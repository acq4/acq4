"""ACQ4-side helpers imported over teleprox by the acq4-mcp server.

Runs inside the ACQ4 process, where the Manager and Qt GUI live. This module has no
dependency on the `mcp` SDK so it imports on every ACQ4 install. `execute` runs
arbitrary code against the live instance; the remaining functions are read-only
inspection helpers.
"""

import ast
import contextlib
import io
import traceback


def _build_namespace() -> dict:
    """Return a fresh globals dict seeded with `man` and `acq4`.

    `man` is the running Manager, or None if no Manager has been created yet (so that
    code not needing the Manager still runs).
    """
    import acq4

    try:
        man = acq4.getManager()
    except Exception:
        man = None
    return {"__name__": "__acq4_mcp__", "acq4": acq4, "man": man}


def _exec_and_capture(code: str, namespace: dict) -> dict:
    """Exec *code* in *namespace*, capturing stdout/stderr and the trailing expression.

    If the final statement is an expression, its value is evaluated and returned as
    `result` (via repr); otherwise `result` is None. Exceptions are caught and returned
    as a formatted `traceback` string rather than propagated.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    result_repr = None
    tb = None

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            parsed = ast.parse(code)
            trailing_expr = None
            if parsed.body and isinstance(parsed.body[-1], ast.Expr):
                trailing_expr = ast.Expression(parsed.body.pop().value)

            exec(compile(parsed, "<acq4-mcp>", "exec"), namespace)
            if trailing_expr is not None:
                value = eval(compile(trailing_expr, "<acq4-mcp>", "eval"), namespace)
                if value is not None:
                    result_repr = repr(value)
        except BaseException:
            tb = traceback.format_exc()

    return {
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "result": result_repr,
        "traceback": tb,
    }


def execute(code: str, gui_thread: bool = False) -> dict:
    """Execute *code* against the live ACQ4 instance and return a result dict.

    The dict has keys: stdout, stderr, result (repr of the trailing expression or None),
    and traceback (a formatted string, or None on success).

    A fresh namespace is built for every call (no state persists between calls), seeded
    with `man` (the Manager) and `acq4`.

    gui_thread selects where the code runs:

    * gui_thread=False (default): run on the calling (teleprox handler) thread. Use this
      for anything blocking or long-running -- device moves, waits, acquisitions, sleeps.
      Running such code on the GUI thread would freeze or deadlock ACQ4.
    * gui_thread=True: marshal onto the Qt GUI thread via run_in_gui_thread, blocking
      until it returns. Use this ONLY for fast, non-blocking access to Qt widgets/objects
      or GUI state. Touching Qt objects from another thread risks a segfault.
    """
    namespace = _build_namespace()

    def run():
        return _exec_and_capture(code, namespace)

    if gui_thread:
        from acq4.util import task

        return task.run_in_gui_thread(run)
    return run()


def _manager():
    """Return the running Manager (raises RuntimeError if none has been created)."""
    import acq4

    return acq4.getManager()


def instance_info() -> dict:
    """Return a lightweight identity/sanity summary of this ACQ4 instance.

    Tolerant of there being no Manager yet (the teleprox server can start before the
    Manager is created), so it is safe to call immediately after connecting.
    """
    import socket

    import acq4

    info = {
        "acq4_version": getattr(acq4, "__version__", None),
        "hostname": socket.gethostname(),
        "has_manager": False,
        "base_dir": None,
        "device_count": None,
    }
    try:
        man = acq4.getManager()
    except Exception:
        return info
    info["has_manager"] = True
    info["base_dir"] = _dir_str(man.getBaseDir())
    info["device_count"] = len(man.listDevices())
    return info


def _dir_str(dir_handle):
    """Return a printable path for a DirHandle, or None."""
    if dir_handle is None:
        return None
    try:
        return dir_handle.name()
    except Exception:
        return str(dir_handle)


def list_devices() -> dict:
    """Return a mapping of device name to its class name for all loaded devices."""
    man = _manager()
    devices = {}
    for name in man.listDevices():
        try:
            devices[name] = type(man.getDevice(name)).__name__
        except Exception as exc:
            devices[name] = f"<error: {exc}>"
    return devices


def list_modules() -> dict:
    """Return currently loaded and configured-but-unloaded module names."""
    man = _manager()
    return {
        "loaded": list(man.listModules()),
        "defined": list(man.listDefinedModules()),
    }


def manager_state() -> dict:
    """Return a summary of Manager storage directories, counts, and config keys.

    Deliberately excludes the module list; use list_modules for that.
    """
    man = _manager()
    try:
        current_dir = _dir_str(man.getCurrentDir())
    except Exception:
        current_dir = None
    return {
        "base_dir": _dir_str(man.getBaseDir()),
        "current_dir": current_dir,
        "device_count": len(man.listDevices()),
        "config_keys": list(getattr(man, "config", {}).keys()),
    }


def get_log(lines: int = 50) -> dict:
    """Return the last *lines* lines of the ACQ4 log file.

    Returns a dict with keys `path` (the log file path or None) and `text`.
    """
    from acq4 import logging_config

    handler = logging_config.log_file_handler
    path = getattr(handler, "baseFilename", None) if handler is not None else None
    if path is None:
        return {"path": None, "text": "No log file is currently configured."}
    try:
        with open(path, "r", errors="replace") as f:
            tail = f.readlines()[-lines:]
    except OSError as exc:
        return {"path": path, "text": f"Could not read log file: {exc}"}
    return {"path": path, "text": "".join(tail)}
