"""Tests for the out-of-process system resource sampler."""

import time

import acq4.util.resource_sampler as rs


def test_sample_now_returns_cpu_memory_and_timestamp():
    sample = rs.sample_now()
    assert set(sample) == {"cpu_percent", "memory_percent", "sampled_at"}
    assert sample["sampled_at"] > 0
    for key in ("cpu_percent", "memory_percent"):
        assert sample[key] is None or 0.0 <= sample[key] <= 100.0


def test_sample_now_survives_a_broken_psutil(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no counters here")

    monkeypatch.setattr(rs.psutil, "cpu_percent", _boom)
    monkeypatch.setattr(rs.psutil, "virtual_memory", _boom)
    sample = rs.sample_now()
    assert sample["cpu_percent"] is None
    assert sample["memory_percent"] is None


def test_latest_reports_no_age_before_the_first_sample():
    # a fresh module has never sampled, so the caller can tell that apart from stale
    assert rs.latest()["age"] is None


def test_start_samples_and_stop_halts(monkeypatch):
    monkeypatch.setattr(
        rs, "sample_now",
        lambda: {"cpu_percent": 5.0, "memory_percent": 50.0, "sampled_at": time.time()},
    )
    try:
        rs.start(interval=0.05)
        deadline = time.time() + 5.0
        while time.time() < deadline and rs.latest()["sampled_at"] is None:
            time.sleep(0.02)
        got = rs.latest()
        assert got["cpu_percent"] == 5.0
        assert got["memory_percent"] == 50.0
        assert got["age"] is not None and got["age"] < 5.0
        assert rs.start(interval=0.05) is True  # idempotent
    finally:
        rs.stop()
    assert rs._thread is None
