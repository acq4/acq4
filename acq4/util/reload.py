"""Hot-reload of changed acq4 modules, keyed on source mtime recorded at load time.

Unlike pyqtgraph.reload.reloadAll, this does not compare against the .pyc, which other
processes may rewrite after an edit.
"""
import os
import sys
import traceback

import pyqtgraph.reload as pg_reload
from pyqtgraph.debug import printExc

_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mtimes = {}  # {.py path: mtime when last loaded}


def __reload__(old):
    _mtimes.update(old["_mtimes"])


def _source_path(mod):
    """Return the .py path of a module under the acq4 package, or None."""
    file = getattr(mod, "__file__", None)
    if file is None:
        return None
    py = os.path.splitext(file)[0] + ".py"
    if not os.path.abspath(py).startswith(_PACKAGE_DIR) or not os.path.isfile(py):
        return None
    return py


def snapshot():
    """Record the current source mtime of every loaded acq4 module."""
    for mod in list(sys.modules.values()):
        py = _source_path(mod)
        if py is not None:
            _mtimes.setdefault(py, os.stat(py).st_mtime)


def reloadChanged(debug=True):
    """Reload acq4 modules whose source changed since they were last loaded.

    Modules first seen here are recorded, not reloaded. Returns {moduleName: (reloaded,
    reason)}. Raises after all modules are attempted if any failed; failed modules stay
    pending so the next call retries them.
    """
    ret = {}
    failed = []
    done = set()
    for name, mod in list(sys.modules.items()):
        py = _source_path(mod)
        if py is None:
            ret[name] = (False, "not an acq4 source module")
            continue
        if py in done:
            continue
        mtime = os.stat(py).st_mtime
        if py not in _mtimes:
            _mtimes[py] = mtime
            ret[name] = (False, "first seen; recorded")
            continue
        if _mtimes[py] == mtime:
            ret[name] = (False, "source unchanged since load")
            continue
        done.add(py)
        try:
            pg_reload.reload(mod, debug=debug)
            _mtimes[py] = mtime
            ret[name] = (True, None)
        except Exception as exc:
            printExc("Error while reloading module %s, skipping\n" % mod)
            failed.append(name)
            ret[name] = (False, "reload failed: %s" % traceback.format_exception_only(type(exc), exc))
    if failed:
        raise Exception("Some modules failed to reload: %s" % ", ".join(failed))
    return ret
