"""Meta Model API adapter for the runtime agent.

Responsibilities: structured calls with constrained decoding, bounded retries with backoff,
per-call usage and cost accounting, redacted call logging, model fallback. Nothing here knows
anything about the plant.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from backend.agent.contracts import response_format

T = TypeVar("T", bound=BaseModel)

# USD per 1M tokens, verified at https://dev.meta.ai/docs/pricing-rate-limits on 2026-10-30.
PRICING_PER_M = {
    "muse-wonder-1.0": {"input": 4.00, "output": 20.00, "cached": 0.20},
    "muse-spark-1.3": {"input": 1.25, "output": 4.25, "cached": 0.15},
    "muse-spark-1.2": {"input": 1.25, "output": 4.25, "cached": 0.15},
}


class MuseError(RuntimeError):
    """Raised when the model cannot produce a valid structured answer within the retry budget."""


def load_api_key() -> str | None:
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"].strip()
    key_file = Path(os.environ.get("MODEL_API_KEY_FILE", Path.home() / "meta.key"))
    if key_file.exists():
        return key_file.read_text().strip() or None
    return None


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    p = PRICING_PER_M.get(model)
    if not p:
        return 0.0
    uncached = max(0, prompt_tokens - cached_tokens)
    return (uncached * p["input"] + cached_tokens * p["cached"] + completion_tokens * p["output"]) / 1_000_000


@dataclass
class CallRecord:
    stage: str
    model: str
    attempt: int
    ok: bool
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    request_messages: list[dict[str, str]] = field(default_factory=list)
    response_text: str | None = None
    ts: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class UsageTotals:
    calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0


class MuseClient:
    """Stage-driven structured calls to Meta Muse. One instance per run."""

    def __init__(
        self,
        model: str | None = None,
        fallback_model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float | None = None,
        max_attempts: int = 4,
        reasoning_effort: str | None = None,
        log_path: Path | None = None,
        max_calls: int | None = None,
    ) -> None:
        key = api_key or load_api_key()
        if not key:
            raise MuseError("No API key: set MODEL_API_KEY, MODEL_API_KEY_FILE, or create ~/meta.key")
        self.model = model or os.getenv("MUSE_MODEL", "muse-spark-1.3")
        self.fallback_model = fallback_model or os.getenv("MUSE_FALLBACK_MODEL", "muse-spark-1.3")
        self.timeout_s = timeout_s or float(os.getenv("MODEL_TIMEOUT_SECONDS", "120"))
        self.max_attempts = max_attempts
        self.reasoning_effort = reasoning_effort or os.getenv("MUSE_REASONING_EFFORT") or None
        self.max_calls = max_calls or int(os.getenv("MAX_MODEL_CALLS_PER_RUN", "40"))
        self.log_path = log_path
        self.totals = UsageTotals()
        self.records: list[CallRecord] = []
        self._client = OpenAI(
            base_url=base_url or os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
            api_key=key,
            timeout=self.timeout_s,
            max_retries=0,  # we own retries so they are logged
        )

    # ------------------------------------------------------------------ public
    def structured(self, stage: str, messages: list[dict[str, str]], contract: type[T]) -> tuple[T, CallRecord]:
        """Call the model and parse into ``contract``. Retries transport errors, rate limits,
        and schema/validation failures (with feedback appended) up to ``max_attempts``.
        Falls back to ``fallback_model`` on the final attempt if it differs."""
        if self.totals.calls >= self.max_calls:
            raise MuseError(f"model call budget exhausted ({self.max_calls})")
        msgs = list(messages)
        last_err: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            model = self.model if attempt < self.max_attempts or self.fallback_model == self.model else self.fallback_model
            t0 = time.time()
            rec = CallRecord(stage=stage, model=model, attempt=attempt, ok=False, latency_s=0.0,
                             request_messages=_redact(msgs))
            try:
                kwargs: dict[str, Any] = {"model": model, "messages": msgs, "response_format": response_format(contract)}
                if self.reasoning_effort:
                    kwargs["reasoning_effort"] = self.reasoning_effort
                resp = self._client.chat.completions.create(**kwargs)
                rec.latency_s = time.time() - t0
                _fill_usage(rec, resp)
                text = resp.choices[0].message.content or ""
                rec.response_text = text
                parsed = contract.model_validate(json.loads(text))
                rec.ok = True
                self._record(rec)
                return parsed, rec
            except (json.JSONDecodeError, ValidationError) as e:
                rec.latency_s = time.time() - t0
                rec.error = f"{type(e).__name__}: {str(e)[:500]}"
                last_err = rec.error
                self._record(rec)
                msgs = msgs + [
                    {"role": "assistant", "content": rec.response_text or ""},
                    {"role": "user", "content": f"Your previous answer was not valid for the required schema: {rec.error}. "
                                                "Answer again with every field present and correctly typed."},
                ]
            except RateLimitError as e:
                rec.latency_s = time.time() - t0
                rec.error = f"RateLimitError: {str(e)[:300]}"
                last_err = rec.error
                self._record(rec)
                time.sleep(_retry_after(e, attempt))
            except (APITimeoutError, APIConnectionError, APIStatusError) as e:
                rec.latency_s = time.time() - t0
                rec.error = f"{type(e).__name__}: {str(e)[:300]}"
                last_err = rec.error
                self._record(rec)
                if isinstance(e, APIStatusError) and 400 <= e.status_code < 500 and e.status_code != 429:
                    # Client error (bad schema, bad param): retrying the same payload is pointless.
                    raise MuseError(rec.error) from e
                time.sleep(_backoff(attempt))
        raise MuseError(f"structured call failed after {self.max_attempts} attempts: {last_err}")

    # ----------------------------------------------------------------- private
    def _record(self, rec: CallRecord) -> None:
        self.records.append(rec)
        self.totals.calls += 1
        if not rec.ok:
            self.totals.failed_calls += 1
        self.totals.prompt_tokens += rec.prompt_tokens
        self.totals.completion_tokens += rec.completion_tokens
        self.totals.reasoning_tokens += rec.reasoning_tokens
        self.totals.cost_usd += rec.cost_usd
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps(rec.to_json()) + "\n")


def _fill_usage(rec: CallRecord, resp: Any) -> None:
    u = getattr(resp, "usage", None)
    if not u:
        return
    rec.prompt_tokens = u.prompt_tokens or 0
    rec.completion_tokens = u.completion_tokens or 0
    details = getattr(u, "completion_tokens_details", None)
    rec.reasoning_tokens = (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
    pdetails = getattr(u, "prompt_tokens_details", None)
    rec.cached_tokens = (getattr(pdetails, "cached_tokens", 0) or 0) if pdetails else 0
    rec.cost_usd = estimate_cost_usd(rec.model, rec.prompt_tokens, rec.completion_tokens, rec.cached_tokens)


def _backoff(attempt: int) -> float:
    return min(30.0, (2 ** attempt) * 0.5 + random.uniform(0, 0.5))


def _retry_after(e: Exception, attempt: int) -> float:
    resp = getattr(e, "response", None)
    ra = None
    try:
        ra = resp.headers.get("retry-after") if resp is not None else None
    except AttributeError:
        ra = None
    if ra:
        try:
            return min(60.0, float(ra))
        except ValueError:
            return _backoff(attempt)
    return _backoff(attempt)


def _redact(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Messages never contain the key, but keep a single choke point for redaction."""
    key = load_api_key()
    if not key:
        return [dict(m) for m in messages]
    return [{**m, "content": m.get("content", "").replace(key, "[REDACTED]")} for m in messages]
