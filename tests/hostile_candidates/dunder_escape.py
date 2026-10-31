# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: classic object-graph escape to os.system via ().__class__.__bases__[0].__subclasses__()."""


def control(obs, state):
    for cls in ().__class__.__bases__[0].__subclasses__():
        if cls.__name__ == "_wrap_close":
            g = cls.__init__.__globals__
            g["system"]("touch /tmp/praxion_hostile_dunder_sentinel.txt")
            return 1.0, {"entries": g["listdir"]("/")}
    for cls in ().__class__.__bases__[0].__subclasses__():
        if "Loader" in cls.__name__ or "Importer" in cls.__name__:
            os_mod = cls.load_module("os")
            os_mod.system("touch /tmp/praxion_hostile_dunder_sentinel.txt")
            return 1.0, state
    return 0.5, state
