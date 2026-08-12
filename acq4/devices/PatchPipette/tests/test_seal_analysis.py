"""Unit tests for SealAnalysis's spontaneous break-in detection.

A cell can rupture into whole-cell configuration while the seal state is still applying suction.
These tests pin the capacitance-based detection that lets the seal state notice, including its
behaviour on the NaN-heavy capacitance traces real test pulses produce.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.seal import SealAnalysis

DATA_DIR = Path(__file__).parent / "data"


class _FakeTestPulse:
    """Minimal stand-in for neuroanalysis PatchClampTestPulse with just the fields we read."""

    def __init__(self, start_time, steady_state_resistance, capacitance):
        self.recording = type("rec", (), {"start_time": start_time})()
        self.analysis = {
            "steady_state_resistance": steady_state_resistance,
            "capacitance": capacitance,
        }


def _analysis(**overrides):
    kwargs = dict(
        success_tau=1.0,
        success_at=1e9,
        hold_tau=0.1,
        hold_at=100e6,
        failure_tau=10.0,
        failure_resistance_threshold=50e6,
        failure_dRdt_threshold=1e6,
        break_in_tau=3.0,
        break_in_capacitance_threshold=10e-12,
        break_in_resistance_ceiling=1e9,
    )
    kwargs.update(overrides)
    return SealAnalysis(**kwargs)


def _trace(times, resistances, capacitances):
    return np.array(list(zip(times, resistances, capacitances)), dtype=float)


def _steady(duration, resistance, capacitance, rate=6.0, start=0.0):
    times = np.arange(start, start + duration, 1.0 / rate)
    return _trace(times, np.full(len(times), resistance), np.full(len(times), capacitance))


def test_no_measurements_means_no_break_in():
    """Before any data arrives the detector must not claim a break-in."""
    assert not _analysis().break_in()


def test_sealing_with_no_membrane_capacitance_is_not_break_in():
    """A seal forming normally reports no capacitance and must never look like a break-in."""
    analysis = _analysis()
    result = analysis.process_measurements(_steady(20.0, 400e6, np.nan))
    assert not result["break_in"].any()
    assert not analysis.break_in()


def test_sustained_membrane_capacitance_is_break_in():
    """Whole-cell capacitance held for seconds, with the seal gone, is a spontaneous break-in."""
    analysis = _analysis()
    result = analysis.process_measurements(_steady(20.0, 100e6, 100e-12))
    assert result["break_in"][-1]
    assert analysis.break_in()


def test_capacitance_above_ceiling_resistance_is_not_break_in():
    """Above the resistance ceiling the pipette is sealed, not broken in, whatever the capacitance."""
    analysis = _analysis()
    result = analysis.process_measurements(_steady(20.0, 2e9, 100e-12))
    assert not result["break_in"].any()
    assert not analysis.break_in()


def test_isolated_capacitance_artifact_does_not_trip_detection():
    """A lone bad capacitance fit during sealing must not be mistaken for a break-in."""
    analysis = _analysis()
    data = _steady(20.0, 400e6, np.nan)
    data[40, 2] = 55e-12  # single artifact reading, like a failed fit mid-seal
    result = analysis.process_measurements(data)
    assert not result["break_in"].any()
    assert not analysis.break_in()


def test_nan_capacitance_does_not_poison_later_detection():
    """A long NaN stretch must not permanently disable detection of a later real break-in."""
    analysis = _analysis()
    analysis.process_measurements(_steady(60.0, 400e6, np.nan))
    assert not analysis.break_in()
    result = analysis.process_measurements(_steady(20.0, 100e6, 100e-12, start=60.0))
    assert result["break_in"][-1]
    assert analysis.break_in()


def test_process_test_pulses_reads_resistance_and_capacitance():
    """process_test_pulses must pull capacitance through, not just resistance."""
    analysis = _analysis()
    tps = [
        _FakeTestPulse(0.0, 400e6, np.nan),
        _FakeTestPulse(0.2, 380e6, 12e-12),
    ]
    result = analysis.process_test_pulses(tps)
    assert result["steady_state_resistance"][0] == pytest.approx(400e6)
    assert result["capacitance"][1] == pytest.approx(12e-12)


def test_recorded_spontaneous_break_in_is_detected():
    """Replay of a real seal that spontaneously broke in must be detected, near when it happened.

    Recorded from the rig: the cell ruptured at t~248.2s (steady state resistance fell from
    ~680MΩ to ~150MΩ while capacitance rose to ~100pF) and the seal state failed to notice,
    holding suction on an established whole-cell until its timeout.
    """
    data = np.load(DATA_DIR / "spontaneous_break_in_seal.npy")
    analysis = _analysis()
    result = analysis.process_measurements(data)

    assert result["break_in"].any(), "the recorded break-in went undetected"
    detected_at = result["time"][result["break_in"]][0]
    assert 248.0 < detected_at < 250.0, f"detected at {detected_at:.2f}s, expected ~248.2s"
    assert result["break_in"][-1], "detection must latch on rather than flicker"


def test_recorded_failed_seal_never_reports_break_in():
    """Replay of a real seal that never broke in must stay silent (negative control)."""
    data = np.load(DATA_DIR / "failed_seal_no_break_in.npy")
    analysis = _analysis()
    result = analysis.process_measurements(data)
    assert not result["break_in"].any()
    assert not analysis.break_in()
