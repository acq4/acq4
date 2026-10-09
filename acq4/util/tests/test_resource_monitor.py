"""Tests for the headless resource-sampling helper used by acq4-mcp health_series."""

import time

import pytest

import acq4.util.resource_monitor as rm


class _App:
    activity_fraction = 0.25


class _Sampler:
    def latest(self, **kwds):
        return {"cpu_percent": 7.0, "memory_percent": 55.0, "age": 0.4}


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    monkeypatch.setattr(rm, "_sampler", None)
    monkeypatch.setattr(rm, "_sampler_proc", None)


def test_sample_resources_reports_cpu_memory_and_qt_activity(monkeypatch):
    monkeypatch.setattr(rm, "_remote_sampler", lambda: _Sampler())
    sample = rm.sample_resources(app=_App())
    assert sample == {"cpu_percent": 7.0, "memory_percent": 55.0, "qt_activity": 25.0}


def test_sample_resources_without_qt_activity(monkeypatch):
    monkeypatch.setattr(rm, "_remote_sampler", lambda: _Sampler())
    assert rm.sample_resources(app=object())["qt_activity"] is None
    assert rm.sample_resources(app=None)["qt_activity"] is None


def test_sampler_failure_is_raised_not_swallowed(monkeypatch):
    def _boom():
        raise RuntimeError("no sampler")

    monkeypatch.setattr(rm, "_remote_sampler", _boom)
    with pytest.raises(RuntimeError, match="no sampler"):
        rm.sample_resources(app=_App())


def test_sample_failure_is_raised_not_swallowed(monkeypatch):
    class _Broken:
        def latest(self, **kwds):
            raise ConnectionError("child went away")

    monkeypatch.setattr(rm, "_remote_sampler", lambda: _Broken())
    with pytest.raises(ConnectionError):
        rm.sample_resources(app=_App())


def test_remote_sampler_is_started_once_and_reused(monkeypatch):
    calls = []

    class _Proc:
        class client:
            @staticmethod
            def _import(name):
                calls.append(name)
                return _Mod()

        proc = type("P", (), {"pid": 1234})()

    class _Mod:
        def start(self, interval, **kwds):
            return True

        def latest(self, **kwds):
            return {"cpu_percent": 1.0, "memory_percent": 2.0}

    import teleprox

    monkeypatch.setattr(teleprox, "start_process", lambda *a, **k: _Proc())
    first = rm._remote_sampler()
    second = rm._remote_sampler()
    assert first is second
    assert calls == ["acq4.util.resource_sampler"]


def test_shutdown_sampler_kills_a_child_that_ignores_stop(monkeypatch):
    events = []

    class _Stubborn:
        def stop(self):
            events.append("stop")

        def poll(self):
            return None  # never exits on request

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(rm, "_sampler_proc", _Stubborn())
    monkeypatch.setattr(rm, "_sampler", object())
    rm.shutdown_sampler()
    assert events == ["stop", "kill"]
    assert rm._sampler is None and rm._sampler_proc is None


def test_shutdown_sampler_leaves_a_clean_exit_alone(monkeypatch):
    events = []

    class _Clean:
        def stop(self):
            events.append("stop")

        def poll(self):
            return 0

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(rm, "_sampler_proc", _Clean())
    rm.shutdown_sampler()
    assert events == ["stop"]


def test_shutdown_sampler_is_a_noop_when_nothing_is_running():
    rm.shutdown_sampler()  # must not raise


def test_gil_probe_reports_min_median_max():
    probe = rm.GilLatencyProbe(interval=0.001, window=10.0)
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline and probe.stats() is None:
            time.sleep(0.05)
        lo, mid, hi = probe.stats()
        assert lo <= mid <= hi
        assert lo >= 0.0  # excess over the requested sleep is never negative
    finally:
        probe.stop()


def test_gil_probe_sees_a_stall():
    probe = rm.GilLatencyProbe(interval=0.001, window=10.0)
    try:
        time.sleep(0.5)
        quiet = probe.stats()[2]
        t_end = time.perf_counter() + 0.25
        while time.perf_counter() < t_end:  # tight loop, no GIL release points
            pass
        stalled = probe.stats()[2]
        assert stalled > quiet
    finally:
        probe.stop()


def test_gil_probe_window_discards_old_samples():
    probe = rm.GilLatencyProbe(interval=0.001, window=0.2)
    try:
        time.sleep(0.4)
        assert probe.stats() is not None
        probe.stop()
        time.sleep(0.4)  # longer than the window, with no new samples arriving
        assert probe.stats() is None
    finally:
        probe.stop()
