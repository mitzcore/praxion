"""Praxion sandbox runner. Executes ONE untrusted controller module, line-delimited JSON over stdio.

This file runs INSIDE the isolation boundary (a locked-down Docker container, or a plain
subprocess in dev-only mode). It is stdlib-only and self-contained so the host can pass it
verbatim via ``python -I -S -c <source>``.

Protocol (one JSON object per line):
    in : {"type": "load", "source": "<module source>"}
    out: {"type": "loaded", "ok": true} | {"type": "loaded", "ok": false, "error": "..."}
    in : {"type": "step", "obs": {...}, "state": {...}}
    out: {"type": "result", "u": <float|null>, "state": {...}, "error": null | "<Type: msg>"}
    in : {"type": "close"}   -> process exits 0

In-process layers (defense in depth; the container is the real boundary):
  1. resource limits: CPU seconds and address space;
  2. the protocol stdout is a private dup'ed fd; fd 1 and sys.stdout point at stderr, so
     candidate output can never be mistaken for a protocol reply;
  3. restricted ``__builtins__`` and an ``__import__`` that only yields ``math``;
  4. a PEP 578 audit hook, armed before candidate code runs, that denies every audited
     operation (open, os.*, subprocess, socket, import, compile, exec of foreign code, ...).
     It catches effects reached through object-graph escapes that bypass layer 3.
"""
import json
import math
import os
import sys

CPU_SECONDS = int(os.environ.get("PRAXION_SANDBOX_CPU_S", "20") or "20")
ADDRESS_SPACE_BYTES = 200 * 1024 * 1024
MAX_STATE_BYTES = 256 * 1024
MAX_ERROR_CHARS = 500


def _apply_rlimits():
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return
    for lim, value in ((resource.RLIMIT_CPU, CPU_SECONDS), (resource.RLIMIT_AS, ADDRESS_SPACE_BYTES)):
        try:
            _soft, hard = resource.getrlimit(lim)
            new_hard = value if hard == resource.RLIM_INFINITY or hard > value else hard
            resource.setrlimit(lim, (min(value, new_hard), new_hard))
        except (ValueError, OSError):
            # macOS refuses to lower RLIMIT_AS; dev-only mode tolerates that.
            pass


_apply_rlimits()

# Private protocol channel. Candidate code that somehow writes to stdout lands on stderr.
_PROTO_OUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr
_PROTO_IN = sys.stdin

_ARMED = [False]
_ALLOWED_CODE = []


def _audit_hook(event, args):
    if not _ARMED[0]:
        return
    if event == "exec" and args and any(args[0] is c for c in _ALLOWED_CODE):
        return
    if event == "import" and args and args[0] == "math":
        return
    raise PermissionError(f"sandbox: operation '{event}' is not permitted")


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and name == "math":
        return math
    raise ImportError(f"sandbox: import of '{name}' is not permitted; only 'math' is available")


_SAFE_BUILTIN_NAMES = (
    "abs", "min", "max", "round", "float", "int", "bool", "len", "range", "enumerate", "zip",
    "sum", "isinstance", "dict", "list", "tuple", "str", "sorted", "reversed", "map", "filter",
    "any", "all", "pow", "divmod", "ValueError", "TypeError", "ZeroDivisionError", "KeyError",
    "Exception", "ArithmeticError", "IndexError", "OverflowError",
)


def _make_builtins():
    import builtins as _b

    safe = {n: getattr(_b, n) for n in _SAFE_BUILTIN_NAMES}
    safe["__import__"] = _guarded_import
    safe["True"] = True
    safe["False"] = False
    safe["None"] = None
    return safe


def _fmt_exc(exc):
    msg = f"{type(exc).__name__}: {exc}"
    return msg[:MAX_ERROR_CHARS]


def _send(obj):
    _PROTO_OUT.write(json.dumps(obj) + "\n")
    _PROTO_OUT.flush()


_CONTROL = [None]


def _load(source):
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    code = compile(source, "<candidate>", "exec", dont_inherit=True)
    namespace = {"__builtins__": _make_builtins(), "__name__": "candidate", "math": math}
    _ALLOWED_CODE.append(code)
    _ARMED[0] = True  # from here on every audited operation is denied
    exec(code, namespace)  # noqa: S102 - this is the sandbox; the code object was compiled above
    fn = namespace.get("control")
    if not callable(fn):
        raise TypeError("module does not define a callable 'control'")
    _CONTROL[0] = fn


def _step(obs, state):
    fn = _CONTROL[0]
    if fn is None:
        return None, state, "RuntimeError: no controller loaded"
    if not isinstance(state, dict):
        state = {}
    out = fn(obs, state)
    if not isinstance(out, (tuple, list)) or len(out) != 2:
        return None, None, f"TypeError: control() must return a (u, state) pair, got {type(out).__name__}"
    u, new_state = out[0], out[1]
    if isinstance(u, bool) or not isinstance(u, (int, float)):
        return None, None, f"TypeError: u must be a float, got {type(u).__name__}"
    try:
        u = float(u)
    except OverflowError:
        return None, None, "ValueError: u is not representable as a float"
    if not math.isfinite(u):
        return None, None, f"ValueError: u must be finite, got {u!r}"
    if not isinstance(new_state, dict):
        return u, None, f"TypeError: state must be a dict, got {type(new_state).__name__}"
    try:
        encoded = json.dumps(new_state)
    except (TypeError, ValueError, RecursionError) as exc:
        return u, None, f"TypeError: state is not JSON-serializable ({_fmt_exc(exc)})"
    if len(encoded) > MAX_STATE_BYTES:
        return u, None, f"ValueError: serialized state is {len(encoded)} bytes; limit is {MAX_STATE_BYTES}"
    return u, json.loads(encoded), None


def main():
    sys.addaudithook(_audit_hook)
    while True:
        line = _PROTO_IN.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
            kind = msg.get("type") if isinstance(msg, dict) else None
        except Exception as exc:  # noqa: BLE001
            _send({"type": "error", "error": "bad request: " + _fmt_exc(exc)})
            continue
        if kind == "close":
            break
        if kind == "load":
            try:
                if _CONTROL[0] is not None or _ARMED[0]:
                    raise RuntimeError("a controller is already loaded")
                _load(msg.get("source"))
                _send({"type": "loaded", "ok": True})
            except BaseException as exc:  # never crash on candidate code
                if isinstance(exc, KeyboardInterrupt):
                    raise
                _send({"type": "loaded", "ok": False, "error": _fmt_exc(exc)})
            continue
        if kind == "step":
            try:
                u, new_state, err = _step(msg.get("obs"), msg.get("state"))
            except BaseException as exc:  # SystemExit, MemoryError, RecursionError, ...
                if isinstance(exc, KeyboardInterrupt):
                    raise
                u, new_state, err = None, None, _fmt_exc(exc)
            try:
                _send({"type": "result", "u": u if err is None else None,
                       "state": new_state if err is None else None, "error": err})
            except BaseException as exc:  # noqa: BLE001
                _send({"type": "result", "u": None, "state": None, "error": "reply failed: " + _fmt_exc(exc)})
            continue
        _send({"type": "error", "error": f"unknown message type {kind!r}"})
    _PROTO_OUT.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
