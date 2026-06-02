"""Unit tests for WholeCellAnalysis, the access-resistance monitor used by the whole cell state.

These tests exercise the pure rolling-average logic that decides when the whole cell
state is "losing access" and should hand off to the clear access state.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.whole_cell import WholeCellAnalysis


class _FakeTestPulse:
    """Minimal stand-in for neuroanalysis PatchClampTestPulse with just the fields we read."""

    def __init__(self, start_time, access_resistance):
        self.recording = type("rec", (), {"start_time": start_time})()
        self.analysis = {"access_resistance": access_resistance}


def _ramp(times, values):
    return np.array(list(zip(times, values)), dtype=float)


def test_stable_low_access_is_not_losing():
    """A cell with steady, low Ra should never be flagged as losing access."""
    analysis = WholeCellAnalysis(access_resistance_threshold=30e6, detection_tau=1.0)
    times = np.arange(0, 10, 0.5)
    measurements = _ramp(times, np.full(len(times), 10e6))
    result = analysis.process_measurements(measurements)
    assert not result["losing_access"].any()
    assert not analysis.is_losing_access()


def test_rising_access_eventually_flags():
    """Ra climbing well past the threshold should eventually flag losing access."""
    analysis = WholeCellAnalysis(access_resistance_threshold=30e6, detection_tau=1.0)
    times = np.arange(0, 20, 0.5)
    values = np.linspace(10e6, 80e6, len(times))
    result = analysis.process_measurements(_ramp(times, values))
    # Early on it is fine, by the end it is clearly losing access.
    assert not result["losing_access"][0]
    assert result["losing_access"][-1]
    assert analysis.is_losing_access()


def test_brief_spike_is_smoothed_out():
    """A single Ra spike should not trip the detector when tau is large."""
    analysis = WholeCellAnalysis(access_resistance_threshold=30e6, detection_tau=10.0)
    times = np.arange(0, 5, 0.5)
    values = np.full(len(times), 10e6)
    values[3] = 200e6  # one-sample artifact
    result = analysis.process_measurements(_ramp(times, values))
    assert not result["losing_access"].any()
    assert not analysis.is_losing_access()


def test_process_test_pulses_reads_access_resistance():
    """process_test_pulses should pull Ra (access_resistance) out of test pulse analysis."""
    analysis = WholeCellAnalysis(access_resistance_threshold=30e6, detection_tau=1.0)
    tps = [_FakeTestPulse(0.0, 10e6), _FakeTestPulse(0.5, 12e6)]
    result = analysis.process_test_pulses(tps)
    assert result["access_resistance"][0] == pytest.approx(10e6)
    assert result["access_resistance"][1] == pytest.approx(12e6)


def test_no_measurements_means_no_loss():
    """Before any data arrives, the detector must not claim loss of access."""
    analysis = WholeCellAnalysis(access_resistance_threshold=30e6, detection_tau=1.0)
    assert not analysis.is_losing_access()
