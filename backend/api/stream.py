"""SSE generators over event_log.jsonl. Live mode tails the file; replay mode re-emits the
stored events paced by their recorded ``ts`` deltas and marks each one ``replay: true``."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from backend.api.bundle import FINAL_STAGES, dumps, read_events


def _sse(rec: dict[str, Any], event: str = "event") -> dict[str, Any]:
    return {"event": event, "id": str(rec.get("seq", "")), "data": dumps(rec)}


async def replay_events(d: Path, speed: float = 1.0, after: int = 0, max_gap_s: float | None = None) -> AsyncIterator[dict]:
    """Re-emit stored events paced by recorded ``ts`` deltas / ``speed``. With ``after``, resume at
    the first event with seq > after, emitted immediately, and pace from that event's ts onward
    (used to change speed mid-replay without restarting)."""
    events = read_events(d)
    speed = max(float(speed), 1e-6)
    started = time.time()
    prev_ts: float | None = None
    for rec in events:
        if int(rec.get("seq", 0)) <= after:
            continue
        ts = float(rec.get("ts") or 0.0)
        if prev_ts is not None:
            gap = max(0.0, ts - prev_ts)
            if max_gap_s is not None:
                gap = min(gap, max_gap_s)
            wait = gap / speed
            if wait > 0.0005:
                await asyncio.sleep(wait)
        prev_ts = ts
        yield _sse({**rec, "replay": True, "replay_started_at": started, "replay_speed": speed})
    yield {"event": "end", "data": dumps({"replay": True, "n_events": len(events), "resumed_after": after})}


async def tail_events(d: Path, after: int = 0, is_active: Callable[[], bool] = lambda: False,
                      poll_s: float = 0.5, idle_close_s: float = 2.0) -> AsyncIterator[dict]:
    """Tail the log. Closes once the run is not executing in this process, the last stage is
    terminal, and nothing new has arrived for ``idle_close_s``."""
    last = after
    stage = None
    idle_since = time.time()
    while True:
        new = read_events(d, after=last)
        for rec in new:
            last = int(rec.get("seq", last))
            if rec.get("kind") == "stage":
                stage = rec.get("to")
            yield _sse(rec)
        if new:
            idle_since = time.time()
        if stage is None:
            stages = [e for e in read_events(d) if e.get("kind") == "stage"]
            stage = stages[-1].get("to") if stages else "NEW"
        settled = stage in FINAL_STAGES or stage == "DEPLOYABLE" or not (d / "event_log.jsonl").exists()
        if not is_active() and settled and time.time() - idle_since >= idle_close_s:
            yield {"event": "end", "data": dumps({"replay": False, "last_seq": last, "stage": stage})}
            return
        await asyncio.sleep(poll_s)
