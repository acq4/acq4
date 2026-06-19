"""Unit tests for WholeCellAnalysis, the access-resistance monitor used by the whole cell state.

These tests exercise the pure rolling-average logic that decides when the whole cell state is
"losing access" and should raise a UI warning so the user can manually initiate 'clear access'.
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


def _analysis(**overrides):
    # max_test_pulse_gap defaults large so plain ramps aren't treated as gapped unless a test
    # explicitly exercises gap handling.
    kwargs = dict(access_resistance_threshold=30e6, detection_tau=1.0, max_test_pulse_gap=1e9)
    kwargs.update(overrides)
    return WholeCellAnalysis(**kwargs)


def test_stable_low_access_is_not_losing():
    """A cell with steady, low Ra should never be flagged as losing access."""
    analysis = _analysis()
    times = np.arange(0, 10, 0.5)
    measurements = _ramp(times, np.full(len(times), 10e6))
    result = analysis.process_measurements(measurements)
    assert not result["losing_access"].any()
    assert not analysis.is_losing_access()


def test_rising_access_eventually_flags():
    """Ra climbing well past the threshold should eventually flag losing access."""
    analysis = _analysis()
    times = np.arange(0, 20, 0.5)
    values = np.linspace(10e6, 80e6, len(times))
    result = analysis.process_measurements(_ramp(times, values))
    # Early on it is fine, by the end it is clearly losing access.
    assert not result["losing_access"][0]
    assert result["losing_access"][-1]
    assert analysis.is_losing_access()


def test_brief_spike_is_smoothed_out():
    """A single Ra spike should not trip the detector when tau is large."""
    analysis = _analysis(detection_tau=10.0)
    times = np.arange(0, 20, 0.5)  # long enough that the detection window has settled
    values = np.full(len(times), 10e6)
    values[3] = 200e6  # one-sample artifact
    result = analysis.process_measurements(_ramp(times, values))
    assert not result["losing_access"].any()
    assert not analysis.is_losing_access()


def test_long_gap_restarts_detection_window():
    """A long pause (ephys held the clamp) must not let a stale reading trip the warning."""
    analysis = _analysis(detection_tau=1.0, max_test_pulse_gap=3.0)
    # Healthy run, then test pulses stop for ~60s while a recording reserves the clamp.
    analysis.process_measurements(_ramp(np.arange(0, 5, 0.5), np.full(10, 10e6)))
    assert not analysis.is_losing_access()
    # First reading after the gap is high, but the window restarts so it must not trip yet.
    analysis.process_measurements(_ramp([65.0], [80e6]))
    assert not analysis.is_losing_access()
    # Only after a fresh detection window of sustained high access does it warn.
    analysis.process_measurements(_ramp(np.arange(65.5, 70, 0.5), np.full(9, 80e6)))
    assert analysis.is_losing_access()


def test_process_test_pulses_reads_access_resistance():
    """process_test_pulses should pull Ra (access_resistance) out of test pulse analysis."""
    analysis = _analysis()
    tps = [_FakeTestPulse(0.0, 10e6), _FakeTestPulse(0.5, 12e6)]
    result = analysis.process_test_pulses(tps)
    assert result["access_resistance"][0] == pytest.approx(10e6)
    assert result["access_resistance"][1] == pytest.approx(12e6)


def test_no_measurements_means_no_loss():
    """Before any data arrives, the detector must not claim loss of access."""
    analysis = _analysis()
    assert not analysis.is_losing_access()
