"""Runtime settings loaded from the environment (see .env.example).

Key loading order: MODEL_API_KEY env -> MODEL_API_KEY_FILE -> ~/meta.key.
The key is never printed or logged; `Settings.__repr__` masks it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional .env support; never required
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(override=False)

DEFAULT_KEY_FILE = Path.home() / "meta.key"


def load_api_key() -> str | None:
    """Return the Meta Model API key, or None if none is configured. Never logs the key."""
    key = os.getenv("MODEL_API_KEY", "").strip()
    if key:
        return key
    path = Path(os.getenv("MODEL_API_KEY_FILE", "") or DEFAULT_KEY_FILE).expanduser()
    try:
        key = path.read_text().strip()
    except OSError:
        return None
    return key or None


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Process-wide settings. Construct via `get_settings()`."""

    meta_base_url: str = "https://api.meta.ai/v1"
    muse_model: str = "muse-wonder-1.0"
    muse_fallback_model: str = "muse-spark-1.3"
    agent_mode: str = "live"  # live | replay | mock
    sandbox: str = "docker"  # docker | subprocess_dev_only
    max_model_calls_per_run: int = 40
    max_experiments_per_run: int = 12
    max_controller_candidates: int = 5
    model_timeout_seconds: int = 120
    artifacts_dir: Path = Path("artifacts/runs")
    api_key: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:  # never leak the key
        return (
            f"Settings(model={self.muse_model!r}, fallback={self.muse_fallback_model!r}, "
            f"agent_mode={self.agent_mode!r}, sandbox={self.sandbox!r}, "
            f"api_key={'set' if self.api_key else 'unset'})"
        )

    __str__ = __repr__


def get_settings() -> Settings:
    """Build Settings from the current environment."""
    return Settings(
        meta_base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
        muse_model=os.getenv("MUSE_MODEL", "muse-wonder-1.0"),
        muse_fallback_model=os.getenv("MUSE_FALLBACK_MODEL", "muse-spark-1.3"),
        agent_mode=os.getenv("PRAXION_AGENT_MODE", "live"),
        sandbox=os.getenv("PRAXION_SANDBOX", "docker"),
        max_model_calls_per_run=_int_env("MAX_MODEL_CALLS_PER_RUN", 40),
        max_experiments_per_run=_int_env("MAX_EXPERIMENTS_PER_RUN", 12),
        max_controller_candidates=_int_env("MAX_CONTROLLER_CANDIDATES", 5),
        model_timeout_seconds=_int_env("MODEL_TIMEOUT_SECONDS", 120),
        artifacts_dir=Path(os.getenv("PRAXION_ARTIFACTS_DIR", "artifacts/runs")),
        api_key=load_api_key(),
    )
