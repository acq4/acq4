"""Hot-reload of modules whose source changed, for source the operator can edit.

Covers acq4 and sibling checkouts, and deliberately excludes the interpreter's own
standard library and installed packages, where re-executing a module is not a reload of
edited code but a re-run of the environment beneath a live process.
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

# importlib.reload re-executes this module's body in its existing namespace, so reading
# through globals() carries the bookkeeping across a reload of reload.py itself. A
# __reload__ hook cannot: pyqtgraph calls it only after a reload that returned, so a body
# that raises partway would leave the table empty and the floor reset to now, silently
# stranding every edit made before it.
#
# The floor is this module's import time rather than true process start. Manager imports
# it during startup, so the gap is milliseconds; a module imported before this one and
# edited inside that gap is missed until its next edit.
_PROCESS_START = globals().get("_PROCESS_START", time.time())
# Keyed by sys.modules name rather than by source path, because reloading happens per
# module object: one file can back two objects, and keying by path makes a permanently
# unreloadable object drag its healthy siblings through a reload on every pass.
_state = globals().get("_state", {})  # {module name: (source path, digest, reloaded cleanly)}

NOT_SOURCE = "not a reloadable source module"
NOT_EDITABLE = "installed package, not editable source"
UNCHANGED = "source unchanged since load"
IGNORED_MAIN = "ignored entry point"
FAILED = "reload failed"  # prefix; callers test with str.startswith

# pyqtgraph's reloadAll only ever handed these to importlib. Without the check, a Cython
# pure-python build's foo.so sitting beside the foo.py it came from is taken for source,
# and reloading it re-runs a C extension's module init.
_SOURCE_SUFFIXES = (".py", ".pyc", ".pyo")


def _normalize(path):
    """Resolve symlinks and case so two spellings of one location compare equal.

    A dev checkout keeps sibling repos in a symlink farm (see pyproject.toml), and an
    environment reached through a symlinked path would otherwise escape the install-root
    test entirely.
    """
    return os.path.normcase(os.path.realpath(path))


def _installed_roots():
    """Directories holding the interpreter's own code and its installed packages.

    Reloading importlib._bootstrap_external, for one, leaves its _bootstrap as None and
    every import afterwards fails.
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

    Re-executing one re-runs argparse, builds a second Manager and re-enters app.exec_()
    inside the running process. Name alone is not enough -- multiprocessing aliases the
    entry point as __mp_main__ -- and identity alone is not enough either: tools/entry.py
    does `from acq4 import __main__`, which loads acq4/__main__.py as its own object
    under its own name while sys.modules["__main__"] is the launcher.
    """
    return name in ("__main__", "__mp_main__") or name.endswith(".__main__")


def _source_entry(mod):
    """Return (source path, mtime) for a module backed by readable .py source, else None.

    Stats once, so a checkout that removes the file cannot race an existence check
    against a later stat.
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

    mtime alone misses an edit that lands within one filesystem tick of the last reload,
    and one restored by tar, rsync -a or cp -p with an older timestamp.
    """
    digest = hashlib.blake2b(digest_size=16)
    with open(py, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _drop_stale_bytecode(py):
    """Remove *py*'s cached bytecode so importlib cannot reuse it.

    CPython validates a .pyc against the source's recorded mtime and size, so an edit
    landing in the same second that leaves the length unchanged still looks valid and
    importlib.reload re-executes the old bytecode. Only a missing cache is resolvable
    here; anything else is reported against the module rather than recorded as a reload
    that may have run stale code.
    """
    try:
        cache = importlib.util.cache_from_source(py)
    except NotImplementedError:
        # An implementation with no cache tag writes no bytecode, so there is nothing
        # that could be stale and nothing to remove.
        return
    try:
        os.remove(cache)
    except FileNotFoundError:
        pass


def _needs_reload(name, py, mtime, signature):
    """Decide from the recorded state for *name* and the source's current digest."""
    recorded = _state.get(name)
    if recorded is None or recorded[0] != py:
        # Either the first time we have looked at this module, or the name now refers to
        # a different file and what we recorded says nothing about it. No digest applies,
        # so the only evidence is the timestamp: anything written since startup is an
        # edit we have not seen.
        #
        # A file already holding an edit before this first look, with a timestamp at or
        # below startup, is therefore invisible -- a restore by tar, rsync -a or cp -p,
        # or an editor that preserves mtime. Nothing is recorded for it either, so the
        # operator's usual move of touching the file does rescue it.
        return mtime > _PROCESS_START
    _recorded_py, recorded_signature, reloaded_cleanly = recorded
    if not reloaded_cleanly:
        # Keep retrying until it reloads without error, whatever its timestamp does.
        return True
    return recorded_signature != signature


def reloadChanged(debug=True):
    """Reload editable modules whose source changed since they were last loaded.

    Scope is every loaded module outside the standard library and site-packages, so acq4
    and sibling source checkouts such as pyqtgraph and teleprox are covered while the
    environment underneath them is not. A checkout that lives *under* the interpreter
    prefix is therefore treated as installed and never reloads.

    A module is reloaded when the digest of its source differs from the one recorded for
    it, or when its last reload failed. Nothing is recorded until a reload is actually
    attempted, so a module seen for the first time is judged on its mtime against this
    module's import time; an edit already on disk with an older timestamp is invisible
    until the file is touched or saved again. A file edited between startup and that
    first look is already current but reloads once anyway; that is the cost of never
    needing a snapshot.

    Returns {moduleName: (reloaded, reason)}, one entry for every name in sys.modules,
    and does not raise for a module that failed: a single unreloadable module would
    otherwise discard the whole report on every call for the rest of the session.
    """
    ret = {}
    candidates = []
    entries = list(sys.modules.items())
    # An entry point can also sit in sys.modules under an ordinary library name, and
    # skipping only the names that look like entry points would let the same object
    # through under that alias.
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
            # Taken before the reload, and recorded afterwards unchanged: a save landing
            # while the reload is in flight must not be recorded as the code now running,
            # or it would be reported unchanged forever.
            signature = digests[py]
            if not _needs_reload(name, py, mtime, signature):
                # Deliberately records nothing. Claiming this digest was "loaded" would
                # assert something we never checked -- we only know the file looks older
                # than startup -- and that claim would then outlive any touch of the
                # file, because content would agree with it forever.
                ret[name] = (False, UNCHANGED)
                continue
            if py not in cleared:
                _drop_stale_bytecode(py)
                cleared.add(py)
        except OSError as exc:
            # The source vanished mid-pass, or its cache could not be cleared. Either way
            # this one module is unreloadable; the rest of the pass is not. Recorded as
            # pending with no digest so the retry is driven by that, not by a timestamp
            # the file may get back when it is restored.
            _state[name] = (py, None, False)
            ret[name] = (False, "%s: %s" % (FAILED, exc))
            continue
        # One file can back more than one module object (spec_from_file_location under a
        # synthetic name), and each object needs its own reload; two names for a single
        # object share one. Keying by identity gets both right, and gives every name a
        # result instead of dropping the aliases.
        if id(mod) in outcomes:
            outcome = outcomes[id(mod)]
        else:
            try:
                pg_reload.reload(mod, debug=debug)
            except Exception as exc:
                # The returned dict is the reliable channel -- a warning would be shown
                # once per process by the default filter -- but the operator still wants
                # the traceback in the log window.
                logger.exception("Error while reloading module %s, skipping", name)
                detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                outcome = (False, "%s: %s" % (FAILED, detail))
            else:
                outcome = (True, None)
            outcomes[id(mod)] = outcome
        # Recorded either way, so a failure is retried by its flag rather than by its
        # timestamp, and a healthy module sharing this file is not dragged along with it.
        _state[name] = (py, signature, outcome[0])
        ret[name] = outcome
    return ret
