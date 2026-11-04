"""Hot-reload of loaded modules whose source changed.

Covers acq4 and other editable checkouts; excludes the stdlib and installed packages.
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

# Read back from globals() so this state survives a reload of this module, including
# one that raises partway (pyqtgraph calls __reload__ hooks only after a reload succeeds).
_PROCESS_START = globals().get("_PROCESS_START", time.time())  # this module's import time
# Keyed by module name, not source path: one file can back two module objects.
_state = globals().get("_state", {})  # {module name: (source path, digest, reloaded cleanly)}

NOT_SOURCE = "not a reloadable source module"
NOT_EDITABLE = "installed package, not editable source"
UNCHANGED = "source unchanged since load"
IGNORED_MAIN = "ignored entry point"
FAILED = "reload failed"  # prefix; callers test with str.startswith

# Only these count as source, so a Cython foo.so beside its foo.py is not reloaded
# (that would re-run the C extension's module init).
_SOURCE_SUFFIXES = (".py", ".pyc", ".pyo")


def _normalize(path):
    """Resolve symlinks and case so two spellings of one location compare equal.

    Without realpath, a path reached through a symlink would not match an install root.
    """
    return os.path.normcase(os.path.realpath(path))


def _installed_roots():
    """Return the normalized stdlib and installed-package directories, each ending in os.sep.

    Modules under these are never reloaded; reloading importlib._bootstrap_external, for
    one, breaks every later import.
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
    """Return True if *name* is a startup-script module (``__main__``, ``__mp_main__``,
    or ``*.__main__``).

    Reloading one would build a second Manager and re-enter app.exec_().
    """
    return name in ("__main__", "__mp_main__") or name.endswith(".__main__")


def _source_entry(mod):
    """Return (source path, mtime) for a module backed by readable .py source, else None."""
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
    """Return a digest of the file at *py*.

    Used instead of mtime, which misses an edit within one filesystem tick of the last
    reload and a file restored with an older timestamp.
    """
    digest = hashlib.blake2b(digest_size=16)
    with open(py, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drop_stale_bytecode(py):
    """Remove *py*'s cached .pyc so the next import compiles the source.

    CPython checks a .pyc only against the source's mtime and size, so a same-second,
    same-length edit would otherwise run the old bytecode. Raises OSError if the cache
    exists but cannot be removed.
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
    """Return True if module *name*, backed by *py*, should be reloaded."""
    recorded = _state.get(name)
    if recorded is None or recorded[0] != py:
        # Not recorded yet, or *name* now maps to a different file: fall back to mtime.
        # An edit already on disk with an mtime before process start is missed until the
        # file is touched.
        return mtime > _PROCESS_START
    _recorded_py, recorded_signature, reloaded_cleanly = recorded
    if not reloaded_cleanly:
        # Retry a failed reload on every pass until it succeeds.
        return True
    return recorded_signature != signature


def reloadChanged(debug=True):
    """Reload editable modules whose source changed since they were last loaded.

    Scope is every loaded module outside the stdlib and site-packages, so sibling source
    checkouts are covered but a checkout under the interpreter prefix is not. A module
    reloads when its source digest differs from the recorded one, or its last reload
    failed; one never seen before reloads if its mtime is later than this module's
    import time.

    Returns {moduleName: (reloaded, reason)} for every name in sys.modules; *reason* is
    None on success, else one of the reason constants above or a string starting with
    FAILED. A failing module does not raise; its traceback is logged.
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
            # Digest taken before the reload, so a save during the reload still reads as
            # a change on the next pass.
            signature = digests[py]
            if not _needs_reload(name, py, mtime, signature):
                # Record nothing, so a later touch of the file still triggers a reload
                # through the mtime check.
                ret[name] = (False, UNCHANGED)
                continue
            if py not in cleared:
                _drop_stale_bytecode(py)
                cleared.add(py)
        except OSError as exc:
            # Mark only this module failed, with no digest, so the next pass retries it
            # regardless of mtime.
            _state[name] = (py, None, False)
            ret[name] = (False, "%s: %s" % (FAILED, exc))
            continue
        # Reload once per module object: aliases share one outcome, while separate
        # objects backed by one file each get their own reload.
        if id(mod) in outcomes:
            outcome = outcomes[id(mod)]
        else:
            try:
                pg_reload.reload(mod, debug=debug)
            except Exception as exc:
                # Also log the traceback, so it appears in the log window.
                logger.exception("Error while reloading module %s, skipping", name)
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                outcome = (False, "%s: %s" % (FAILED, detail))
            else:
                outcome = (True, None)
            outcomes[id(mod)] = outcome
        # Recorded on success and failure; a failure is retried via its flag, not mtime.
        _state[name] = (py, signature, outcome[0])
        ret[name] = outcome
    return ret
