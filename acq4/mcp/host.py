"""ACQ4-side helpers imported over teleprox by the acq4-mcp server.

Runs inside the ACQ4 process, where the Manager and Qt GUI live. This module has no
dependency on the `mcp` SDK so it imports on every ACQ4 install. `execute` runs
arbitrary code against the live instance; the remaining functions are read-only
inspection helpers.
"""

import ast
import collections
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


_PERSISTENT_NS = None


def _get_namespace() -> dict:
    """Return the process-global persistent exec namespace, building it on first use.

    State set by one execute() call is visible to the next. `man` is re-resolved when it
    was None (no Manager existed at build time) so it heals once a Manager appears,
    without disturbing user-defined variables. Call reset_namespace() to start clean.
    """
    global _PERSISTENT_NS
    if _PERSISTENT_NS is None:
        _PERSISTENT_NS = _build_namespace()
    if _PERSISTENT_NS.get("man") is None:
        import acq4

        try:
            _PERSISTENT_NS["man"] = acq4.getManager()
        except Exception:
            pass
    return _PERSISTENT_NS


def reset_namespace() -> dict:
    """Discard the persistent exec namespace so the next execute() starts fresh."""
    global _PERSISTENT_NS
    _PERSISTENT_NS = None
    return {"reset": True}


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

    # redirect_stdout/redirect_stderr swap the process-global sys.stdout/sys.stderr, so
    # for off-GUI (threaded) exec this also captures -- and thus steals -- concurrent
    # print()s emitted by other threads while the code runs; their output may end up in
    # this result or be lost from wherever it was meant to go.
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

    A single persistent namespace is shared across calls (state persists); call
    reset_namespace() to clear it. The namespace is seeded with `man` (the Manager) and
    `acq4`.

    gui_thread selects where the code runs:

    * gui_thread=False (default): run on the calling (teleprox handler) thread. Use this
      for anything blocking or long-running -- device moves, waits, acquisitions, sleeps.
      Running such code on the GUI thread would freeze or deadlock ACQ4.
    * gui_thread=True: marshal onto the Qt GUI thread via run_in_gui_thread, blocking
      until it returns. Use this ONLY for fast, non-blocking access to Qt widgets/objects
      or GUI state. Touching Qt objects from another thread risks a segfault.
    """
    namespace = _get_namespace()

    def run():
        return _exec_and_capture(code, namespace)

    if gui_thread:
        from acq4.util import task

        return task.run_in_gui_thread(run)
    return run()


def reload_libraries() -> dict:
    """Hot-reload changed Python modules in the running ACQ4 process.

    Mirrors the Manager window's "Reload Libraries" button (Ctrl+R): calls
    pyqtgraph.reload.reloadAll, which re-execs every loaded module whose source file is
    newer than its compiled cache and rebinds existing functions/methods/instances to the
    updated code. Runs on the Qt GUI thread, exactly as the button does, because it
    mutates live (possibly Qt) objects.

    Returns a dict with keys: reloaded (sorted list of module names actually reloaded),
    skipped (count of modules left unchanged), error (a formatted message if the reload
    raised -- some modules may still have reloaded before it did), and output (the
    reloader's captured debug log). When the reload raises, reloadAll discards its
    per-module dict, so reloaded/skipped are None and only output/error describe what
    happened.
    """
    import pyqtgraph.reload as reload

    from acq4.util import task

    def run():
        buf = io.StringIO()
        error = None
        results = None
        # debug=True prints one line per reloaded module; redirect_stdout captures those
        # so the summary can carry the reload log back to the caller.
        with contextlib.redirect_stdout(buf):
            try:
                results = reload.reloadAll(debug=True)
            except Exception:
                error = traceback.format_exc()
        summary = {"output": buf.getvalue(), "error": error}
        if results is None:
            summary["reloaded"] = None
            summary["skipped"] = None
        else:
            summary["reloaded"] = sorted(
                name for name, (ok, _reason) in results.items() if ok
            )
            summary["skipped"] = sum(
                1 for _name, (ok, _reason) in results.items() if not ok
            )
        return summary

    return task.run_in_gui_thread(run)


def _manager():
    """Return the running Manager (raises RuntimeError if none has been created)."""
    import acq4

    return acq4.getManager()


def _profiler_tabs():
    """Return the live Profiler module's ProfilerTabs widget, loading it if needed.

    Loads the `Profiler` module (opening its window) when it is not already loaded, so
    profiling data collects into the same window the human sees. Must be called on the
    GUI thread.
    """
    man = _manager()
    for name in man.listModules():
        mod = man.getModule(name)
        if type(mod).__name__ == "Profiler" and hasattr(mod, "profiler_tabs"):
            return mod.profiler_tabs
    mod = man.loadModule("Profiler")
    return mod.profiler_tabs


def _top_functions(function_lookup, top=15):
    """Rank functions in a ProfileAnalyzer lookup by summed call duration (desc).

    function_lookup maps a function_key to {"calls": [CallRecord, ...]}. Pure: takes only
    the lookup dict so it is testable without a live profile.
    """
    rows = []
    for calls in (data["calls"] for data in function_lookup.values()):
        durations = [c.duration for c in calls if c.duration is not None]
        if not durations:
            continue
        first = calls[0]
        rows.append(
            {
                "function": first.display_name,
                "filename": first.filename,
                "lineno": first.lineno,
                "n_calls": len(durations),
                "total_seconds": sum(durations),
            }
        )
    rows.sort(key=lambda r: r["total_seconds"], reverse=True)
    return rows[:top]


def profile_functions(seconds=10.0, top=15):
    """Profile all-thread function calls for `seconds`, return the hottest functions.

    Drives the live Profiler window's function profiler (opening it if needed), so the
    same call tree is visible to the human. Must run off the GUI thread (it sleeps for
    the profiling window); the start/stop touch the widget via run_in_gui_thread.
    """
    import time

    from acq4.util import task
    from rtprofile.profiler import ProfileAnalyzer

    tabs = task.run_in_gui_thread(_profiler_tabs)
    fp = tabs.function_profiler
    if not hasattr(fp, "start_session"):
        return {
            "error": "Installed rtprofile lacks the headless start_session API; update rtprofile."
        }
    task.run_in_gui_thread(fp.start_session, None, None)
    time.sleep(seconds)
    result = task.run_in_gui_thread(fp.stop_session)
    analyzer = ProfileAnalyzer(result.profile)
    return {
        "session": result.name,
        "duration_seconds": result.profile_duration,
        "top_functions": _top_functions(analyzer.build_function_lookup(), top=top),
    }


def _summarize_heap(heap_stats, top=15):
    """Summarize a guppy heap (or heap diff): total bytes and the top types by size.

    Pure aside from reading the guppy object's `.size`/`.bytype` interface, so it is
    testable with a fake exposing those.
    """
    by_type = heap_stats.bytype
    rows = []
    for i in range(min(top, len(by_type))):
        stat = by_type[i]
        rows.append({"type": str(stat.kind), "count": stat.count, "bytes": stat.size})
    return {"total_bytes": heap_stats.size, "top_types": rows}


def memory_snapshot(name=None, top=15):
    """Take a guppy heap snapshot into the live Profiler window and summarize it.

    Repeated calls accumulate snapshots in the window (the memory-over-time series). When
    a prior snapshot exists, `growth` summarizes the heap increase since the last one.
    Must run on the GUI thread path via run_in_gui_thread (touches the widget).
    """
    from acq4.util import task

    tabs = task.run_in_gui_thread(_profiler_tabs)
    mp = tabs.memory_profiler
    if not hasattr(mp, "take_snapshot"):
        return {
            "error": "Installed rtprofile lacks the headless take_snapshot API; update rtprofile."
        }
    previous = mp.snapshots[-1] if mp.snapshots else None
    try:
        snapshot = task.run_in_gui_thread(mp.take_snapshot, name)
    except RuntimeError as exc:
        return {"error": str(exc)}
    if not snapshot.is_valid:
        return {"name": snapshot.name, "error": snapshot.error_message}
    out = {
        "name": snapshot.name,
        "snapshot": _summarize_heap(snapshot.heap_stats, top=top),
    }
    if previous is not None and previous.is_valid:
        out["growth_since"] = previous.name
        out["growth"] = _summarize_heap(
            snapshot.heap_stats - previous.heap_stats, top=top
        )
    return out


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


def health_series(seconds=10.0, interval=1.0):
    """Sample CPU/memory/Qt-activity/event-loop-latency every `interval` for `seconds`.

    Returns a time series. Must run off the GUI thread (it sleeps between samples);
    latency is a GUI-thread round-trip timing per sample.
    """
    import time

    from acq4.util import task
    from acq4.util.Qt import QApplication
    from acq4.util.resource_monitor import sample_resources

    app = QApplication.instance()
    samples = []
    start = time.perf_counter()
    n = max(1, int(seconds / interval))
    for _ in range(n):
        t0 = time.perf_counter()
        task.run_in_gui_thread(lambda: None)  # measure GUI-thread responsiveness
        latency_ms = (time.perf_counter() - t0) * 1000
        sample = sample_resources(app=app)
        sample["t"] = time.perf_counter() - start
        sample["latency_ms"] = latency_ms
        samples.append(sample)
        time.sleep(interval)
    return {"interval": interval, "samples": samples}


def profile_qt_events(seconds=10.0, top=15):
    """Profile the Qt event loop for `seconds`; return the busiest event types.

    Requires ACQ4 started with --qt-profile (ProfiledQApplication); otherwise returns an
    error dict. Drives the live Profiler window's Qt tab.
    """
    import time

    from acq4.util import task

    tabs = task.run_in_gui_thread(_profiler_tabs)
    qp = tabs.qt_profiler
    if not hasattr(qp, "start_session"):
        return {
            "error": "Installed rtprofile lacks the headless start_session API; update rtprofile."
        }
    try:
        task.run_in_gui_thread(qp.start_session, None, False)
    except RuntimeError as exc:
        return {"error": str(exc)}
    time.sleep(seconds)
    profile = task.run_in_gui_thread(qp.stop_session)
    stats = profile.get_statistics(group_by="type")
    return {"session": profile.name, "top_events": stats[:top]}


def get_log(lines: int = 50) -> dict:
    """Return the last *lines* lines of the ACQ4 log file.

    Returns a dict with keys `path` (the log file path or None) and `text`. A
    non-positive *lines* (0 or negative) means "no lines" and yields empty `text`
    without touching the file.
    """
    from acq4 import logging_config

    handler = logging_config.log_file_handler
    path = getattr(handler, "baseFilename", None) if handler is not None else None
    if path is None:
        return {"path": None, "text": "No log file is currently configured."}
    if lines <= 0:
        return {"path": path, "text": ""}
    try:
        with open(path, "r", errors="replace") as f:
            # deque(maxlen=lines) keeps only the last `lines` lines in memory as it
            # streams the file, rather than materializing the whole file into a list
            # just to slice off the tail.
            tail = collections.deque(f, maxlen=lines)
    except OSError as exc:
        return {"path": path, "text": f"Could not read log file: {exc}"}
    return {"path": path, "text": "".join(tail)}
