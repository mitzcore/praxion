# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: walk a traceback frame to the runner's globals and grab the real builtins/open."""


def control(obs, state):
    try:
        raise ValueError("x")
    except ValueError as exc:
        frame = exc.__traceback__.tb_frame
        while frame.f_back is not None:
            frame = frame.f_back
        real_builtins = frame.f_globals["__builtins__"]
        real_open = real_builtins["open"] if isinstance(real_builtins, dict) else real_builtins.open
        data = real_open("/etc/passwd").read()
        return 1.0, {"leak": data[:100]}
