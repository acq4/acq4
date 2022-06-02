# -*- coding: utf-8 -*-
from __future__ import print_function

import glob
import os
import sys

# singleton MMCorePy instance
_mmc = None

# default location to search for micromanager
microManagerPaths = glob.glob("C:\\Program Files\Micro-Manager*")


class MMCWrapper:
    """Wraps MMCorePy to raise more helpful exceptions
    """

    def __init__(self, mmc):
        self.__mmc = mmc
        self.__wrapper_cache = {}

    def __getattr__(self, name):
        attr = getattr(self.__mmc, name)
        if not callable(attr):
            return attr

        if name in self.__wrapper_cache:
            return self.__wrapper_cache[name]

        def fn(*args, **kwds):
            try:
                return attr(*args, **kwds)
            except RuntimeError as exc:
                if exc.args and hasattr(exc.args[0], 'getFullMsg'):
                    msg = exc.args[0].getFullMsg()
                else:
                    msg = exc
                raise RuntimeError(f"{msg} (calling mmc.{name} with args {args} {kwds})")

        fn.__name__ = name + "_wrapped"
        self.__wrapper_cache[name] = fn
        return fn


def getMMCorePy(path=None):
    """Return a singleton MMCorePy instance that is shared by all devices for accessing micromanager.
    """
    global _mmc
    if _mmc is None:
        if path is None:
            paths = microManagerPaths
        else:
            paths = [path]

        try:
            import pymmcore

            _mmc = MMCWrapper(pymmcore.CMMCore())
            _mmc.setDeviceAdapterSearchPaths(paths)
            sys.path.extend(paths)
            os.environ["PATH"] = os.environ["PATH"] + ";" + ';'.join(paths)
        except ImportError:

            try:
                import MMCorePy
            except ImportError:
                if sys.platform != "win32":
                    raise
                # MM does not install itself to standard path. User should take care of this,
                # but we can make a guess...
                sys.path.append(path)
                os.environ["PATH"] = os.environ["PATH"] + ";" + path
                try:
                    import MMCorePy
                finally:
                    sys.path.pop()

            _mmc = MMCorePy.CMMCore()

    return _mmc
