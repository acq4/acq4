"""Hot-reload of modules whose source changed, for source the operator can edit.

Covers acq4 and sibling checkouts; excludes the stdlib and installed packages, where
re-executing a module is not a reload of edited code.
"""
import hashlib
import importlib.util
import inspect
import logging
import os
import site
import sys
import sysconfig
import time
import traceback

import pyqtgraph.reload as pg_reload

logger = logging.getLogger("acq4")

# Read through globals() so the bookkeeping survives a reload of reload.py itself; a
# __reload__ hook would not, since pyqtgraph calls it only after a reload that returned.
_PROCESS_START = globals().get("_PROCESS_START", time.time())  # this module's import time
# Keyed by module name, not source path: one file can back two module objects.
_state = globals().get("_state", {})  # {module name: (source path, digest, reloaded cleanly)}

NOT_SOURCE = "not a reloadable source module"
NOT_EDITABLE = "installed package, not editable source"
UNCHANGED = "source unchanged since load"
IGNORED_MAIN = "ignored entry point"
FAILED = "reload failed"  # prefix; callers test with str.startswith

# Without this, a Cython build's foo.so beside its foo.py is taken for source, and
# reloading it re-runs a C extension's module init.
_SOURCE_SUFFIXES = (".py", ".pyc", ".pyo")


def _normalize(path):
    """Resolve symlinks and case so two spellings of one location compare equal.

    Dev checkouts keep sibling repos in a symlink farm, which would otherwise escape the
    install-root test.
    """
    return os.path.normcase(os.path.realpath(path))


def _installed_roots():
    """Directories holding the interpreter's own code and its installed packages.

    Reloading importlib._bootstrap_external leaves its _bootstrap None and every later
    import fails.
    """
    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}
    paths = sysconfig.get_paths()
    roots.update(paths.get(name) for name in ("stdlib", "platstdlib", "purelib", "platlib"))
    try:
        roots.update(site.getsitepackages())
    except AttributeError:
        # Not available inside a virtualenv built without it.
        pass
    # pip install --user lands outside every sysconfig path and every prefix.
    roots.add(site.getusersitepackages())
    return tuple(sorted(_normalize(root) + os.sep for root in roots if root))


_INSTALLED_ROOTS = _installed_roots()


def _is_entry_point(name):
    """Is *name* a module whose body is a startup script rather than a library?

    Re-executing one builds a second Manager and re-enters app.exec_() in this process.
    Checked by name and by identity: neither catches every alias on its own.
    """
    return name in ("__main__", "__mp_main__") or name.endswith(".__main__")


def _source_entry(mod):
    """Return (source path, mtime) for a module backed by readable .py source, else None.

    Stats once, so a file removed mid-pass cannot race an existence check against a stat.
    """
    if not inspect.ismodule(mod):
        # sys.modules also holds lazy-import shims and module proxies.
        return None
    file = getattr(mod, "__file__", None)
    if file is None or not file.endswith(_SOURCE_SUFFIXES):
        return None
    py = os.path.abspath(os.path.splitext(file)[0] + ".py")
    try:
        return py, os.stat(py).st_mtime
    except OSError:
        # Namespace package, .pyc-only install, or source removed since it was imported.
        return None


def _signature(py):
    """A digest of the source, so an edit is seen however its timestamp behaves.

    mtime misses an edit within one filesystem tick of the last reload, and one restored
    with an older timestamp.
    """
    digest = hashlib.blake2b(digest_size=16)
    with open(py, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drop_stale_bytecode(py):
    """Remove *py*'s cached bytecode so importlib cannot reuse it.

    CPython validates a .pyc against the source's mtime and size, so a same-second edit
    that preserves the length still looks valid and the old bytecode is re-executed.
    """
    try:
        cache = importlib.util.cache_from_source(py)
    except NotImplementedError:
        # No cache tag means no bytecode written, so nothing can be stale.
        return
    try:
        os.remove(cache)
    except FileNotFoundError:
        pass


def _needs_reload(name, py, mtime, signature):
    """Decide from the recorded state for *name* and the source's current digest."""
    recorded = _state.get(name)
    if recorded is None or recorded[0] != py:
        # First look, or the name now refers to a different file: no digest applies, so
        # the timestamp is the only evidence. An edit already on disk with an older
        # timestamp is invisible until the file is touched.
        return mtime > _PROCESS_START
    _recorded_py, recorded_signature, reloaded_cleanly = recorded
    if not reloaded_cleanly:
        # Keep retrying until it reloads without error, whatever its timestamp does.
        return True
    return recorded_signature != signature


def reloadChanged(debug=True):
    """Reload editable modules whose source changed since they were last loaded.

    Scope is every loaded module outside the stdlib and site-packages, so sibling source
    checkouts are covered but a checkout under the interpreter prefix is not. A module
    reloads when its source digest differs from the recorded one, or its last reload
    failed; one never seen before is judged on mtime against this module's import time.

    Returns {moduleName: (reloaded, reason)} for every name in sys.modules. Does not
    raise on failure: one unreloadable module would discard the whole report.
    """
    ret = {}
    candidates = []
    entries = list(sys.modules.items())
    # An entry point can also sit in sys.modules under an ordinary library name.
    entry_ids = {id(mod) for name, mod in entries if _is_entry_point(name)}
    for name, mod in entries:
        if _is_entry_point(name) or id(mod) in entry_ids:
            ret[name] = (False, IGNORED_MAIN)
            continue
        source = _source_entry(mod)
        if source is None:
            ret[name] = (False, NOT_SOURCE)
            continue
        py, mtime = source
        if _normalize(py).startswith(_INSTALLED_ROOTS):
            ret[name] = (False, NOT_EDITABLE)
            continue
        candidates.append((name, mod, py, mtime))

    digests = {}
    cleared = set()
    outcomes = {}
    for name, mod, py, mtime in candidates:
        try:
            if py not in digests:
                digests[py] = _signature(py)
            # Taken before the reload: a save landing mid-reload must not be recorded as
            # the code now running, or it would read as unchanged forever.
            signature = digests[py]
            if not _needs_reload(name, py, mtime, signature):
                # Records nothing: claiming this digest was loaded would assert what we
                # never checked, and would outlive any later touch of the file.
                ret[name] = (False, UNCHANGED)
                continue
            if py not in cleared:
                _drop_stale_bytecode(py)
                cleared.add(py)
        except OSError as exc:
            # This one module is unreloadable; the rest of the pass is not. Recorded
            # pending with no digest, so the retry is driven by that and not by mtime.
            _state[name] = (py, None, False)
            ret[name] = (False, "%s: %s" % (FAILED, exc))
            continue
        # One file can back several module objects, each needing its own reload, while
        # two names for one object share a reload. Identity gets both right.
        if id(mod) in outcomes:
            outcome = outcomes[id(mod)]
        else:
            try:
                pg_reload.reload(mod, debug=debug)
            except Exception as exc:
                # The returned dict is the reliable channel, but the operator still
                # wants the traceback in the log window.
                logger.exception("Error while reloading module %s, skipping", name)
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                outcome = (False, "%s: %s" % (FAILED, detail))
            else:
                outcome = (True, None)
            outcomes[id(mod)] = outcome
        # Recorded either way, so a failure is retried by its flag and not by mtime.
        _state[name] = (py, signature, outcome[0])
        ret[name] = outcome
    return ret
