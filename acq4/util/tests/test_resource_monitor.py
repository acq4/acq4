"""Tests for the headless resource-sampling helper used by acq4-mcp health_series."""

import acq4.util.resource_monitor as rm


class _App:
    activity_fraction = 0.25


def test_sample_resources_reports_cpu_and_memory(monkeypatch):
    monkeypatch.setattr(rm.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(
        rm.psutil, "virtual_memory", lambda: type("M", (), {"percent": 40.0})()
    )
    sample = rm.sample_resources(app=_App())
    assert sample["cpu_percent"] == 12.5
    assert sample["memory_percent"] == 40.0
    assert sample["qt_activity"] == 25.0


def test_sample_resources_without_qt_activity(monkeypatch):
    monkeypatch.setattr(rm.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(
        rm.psutil, "virtual_memory", lambda: type("M", (), {"percent": 2.0})()
    )
    sample = rm.sample_resources(app=object())
    assert sample["qt_activity"] is None
