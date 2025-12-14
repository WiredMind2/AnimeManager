import os


def windows():
    windows = []
    ignore = ("__init__", "__pycache__")
    root = os.path.dirname(__file__)
    for f in os.listdir(root):
        name = f.split(".py")[0]
        if name not in ignore:
            try:
                try:
                    exec("from . import " + name)
                except ImportError:
                    exec("from windows import " + name)
            except Exception as e:
                raise
            module = globals()[name]
            funcname = name[0].upper() + name[1:]
            func = getattr(module, funcname)
            windows.append(func)

    return windows
