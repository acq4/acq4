"""Unit tests for the pure aggregation/formatting helpers behind acq4-mcp profiling.

The live Qt/Manager/guppy collection path is verified manually; these cover the
data-shaping helpers with fabricated inputs.
"""

from acq4.mcp import host


class _Call:
    def __init__(self, duration, display_name, filename, lineno):
        self.duration = duration
        self.display_name = display_name
        self.filename = filename
        self.lineno = lineno


def test_top_functions_sorts_by_total_time_desc():
    lookup = {
        ("a.py", 10, "slow"): {
            "calls": [_Call(0.5, "slow", "a.py", 10), _Call(0.5, "slow", "a.py", 10)]
        },
        ("b.py", 20, "fast"): {"calls": [_Call(0.01, "fast", "b.py", 20)]},
    }
    rows = host._top_functions(lookup, top=10)
    assert [r["function"] for r in rows] == ["slow", "fast"]
    assert rows[0]["n_calls"] == 2
    assert abs(rows[0]["total_seconds"] - 1.0) < 1e-9


def test_top_functions_truncates_to_top_n():
    lookup = {
        (f"f{i}.py", i, f"fn{i}"): {"calls": [_Call(float(i), f"fn{i}", f"f{i}.py", i)]}
        for i in range(1, 6)
    }
    rows = host._top_functions(lookup, top=2)
    assert len(rows) == 2
    assert rows[0]["function"] == "fn5"


def test_top_functions_handles_c_call_keys():
    lookup = {
        ("c_call", "builtins.len", "builtins"): {
            "calls": [_Call(0.2, "len", "<builtin>", 0)]
        }
    }
    rows = host._top_functions(lookup, top=5)
    assert rows[0]["function"] == "len"
    assert rows[0]["total_seconds"] == 0.2


class _TypeStat:
    def __init__(self, kind, count, size):
        self.kind = kind
        self.count = count
        self.size = size


class _Heap:
    def __init__(self, size, rows):
        self.size = size
        self.bytype = rows  # list is indexable + has len, like a guppy partition


def test_summarize_heap_reports_total_and_top_types():
    heap = _Heap(300, [_TypeStat("dict", 2, 200), _TypeStat("list", 5, 100)])
    summary = host._summarize_heap(heap, top=1)
    assert summary["total_bytes"] == 300
    assert summary["top_types"] == [{"type": "dict", "count": 2, "bytes": 200}]


def test_health_series_collects_expected_sample_count(monkeypatch):
    import time

    import acq4.mcp.host as h
    import acq4.util.resource_monitor as rm
    from acq4.util import Qt, task

    # health_series does local `import time`, `from acq4.util import task`, `from
    # acq4.util.Qt import QApplication`, and `from acq4.util.resource_monitor import
    # sample_resources` at call time, so patching each on its home module takes effect.
    #
    # A bare object() stand-in for the app would break pytest-qt's autouse hook, which
    # calls QApplication.instance().processEvents() after every test; give the fake a
    # no-op processEvents so that hook keeps working while QApplication.instance is
    # patched for the duration of this test.
    class _FakeApp:
        def processEvents(self):
            pass

    monkeypatch.setattr(Qt.QApplication, "instance", staticmethod(lambda: _FakeApp()))
    monkeypatch.setattr(task, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(
        rm,
        "sample_resources",
        lambda app=None: {
            "cpu_percent": 1.0,
            "memory_percent": 2.0,
            "qt_activity": None,
        },
    )
    monkeypatch.setattr(time, "sleep", lambda s: None)

    out = h.health_series(seconds=3.0, interval=1.0)
    assert len(out["samples"]) == 3
    assert out["samples"][0]["latency_ms"] >= 0


def test_profile_functions_returns_error_when_rtprofile_lacks_api(monkeypatch):
    """profile_functions should report {"error": ...} rather than raise when the
    installed rtprofile lacks the headless start_session API (env not ready)."""
    import acq4.mcp.host as h
    from acq4.util import task

    class _FakeFunctionProfiler:
        pass  # no start_session

    class _FakeTabs:
        function_profiler = _FakeFunctionProfiler()

    monkeypatch.setattr(task, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(h, "_profiler_tabs", lambda: _FakeTabs())

    result = h.profile_functions(seconds=1.0)
    assert "error" in result


def test_memory_snapshot_returns_error_when_rtprofile_lacks_api(monkeypatch):
    """memory_snapshot should report {"error": ...} rather than raise when the
    installed rtprofile lacks the headless take_snapshot API (env not ready)."""
    import acq4.mcp.host as h
    from acq4.util import task

    class _FakeMemoryProfiler:
        pass  # no take_snapshot

    class _FakeTabs:
        memory_profiler = _FakeMemoryProfiler()

    monkeypatch.setattr(task, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.setattr(h, "_profiler_tabs", lambda: _FakeTabs())

    result = h.memory_snapshot()
    assert "error" in result
