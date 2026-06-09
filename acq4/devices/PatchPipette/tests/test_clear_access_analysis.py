"""Unit tests for ClearAccessAnalysis, the recovery monitor used by the clear access state.

The clear access state applies recovery pulses (and optional zaps) to drop a climbing access
resistance back down. This analysis owns the decisions the state acts on:
 - access recovered (Ra back below threshold -> success, return to whole cell)
 - repairing (Ri declining -> pause pulsing until the membrane recovers)
 - cell lost (Ri collapsed below floor -> give up, go to fouled)
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.PatchPipette.states.clear_access import ClearAccessAnalysis


class _FakeTestPulse:
    """Minimal stand-in for neuroanalysis PatchClampTestPulse with just the fields we read."""

    def __init__(self, start_time, access_resistance, input_resistance):
        self.recording = type("rec", (), {"start_time": start_time})()
        self.analysis = {
            "access_resistance": access_resistance,
            "input_resistance": input_resistance,
        }


def _measurements(times, ra, ri):
    return np.array(list(zip(times, ra, ri)), dtype=float)


def _default_analysis(**overrides):
    kwargs = dict(
        access_recovered_threshold=25e6,
        input_resistance_loss_threshold=50e6,
        input_resistance_decline_threshold=-0.01,
        detection_tau=1.0,
        repair_tau=10.0,
    )
    kwargs.update(overrides)
    return ClearAccessAnalysis(**kwargs)


def test_access_recovery_is_detected():
    """Ra falling back below the recovered threshold (with healthy Ri) is a success."""
    analysis = _default_analysis()
    times = np.arange(0, 20, 0.5)
    ra = np.linspace(50e6, 10e6, len(times))
    ri = np.full(len(times), 300e6)
    result = analysis.process_measurements(_measurements(times, ra, ri))
    assert not result["recovered"][0]
    assert analysis.access_recovered()
    assert not analysis.cell_lost()
    assert not analysis.is_repairing()


def test_healthy_but_high_access_needs_more_pulses():
    """Steady high Ra with healthy Ri: not recovered, not lost, not repairing (keep pulsing)."""
    analysis = _default_analysis()
    times = np.arange(0, 20, 0.5)
    ra = np.full(len(times), 80e6)
    ri = np.full(len(times), 300e6)
    analysis.process_measurements(_measurements(times, ra, ri))
    assert not analysis.access_recovered()
    assert not analysis.cell_lost()
    assert not analysis.is_repairing()


def test_declining_input_resistance_triggers_repair_pause():
    """A steadily dropping Ri should flag repairing so the state pauses pulsing."""
    analysis = _default_analysis()
    times = np.arange(0, 10, 0.5)
    ra = np.full(len(times), 80e6)  # still high, not recovered
    # ~3% drop per sample stays comfortably above the loss floor but well past the decline threshold.
    ri = 300e6 * (0.97 ** np.arange(len(times)))
    result = analysis.process_measurements(_measurements(times, ra, ri))
    assert result["repairing"][-1]
    assert analysis.is_repairing()
    assert not analysis.cell_lost()


def test_recovered_input_resistance_clears_repair_pause():
    """Once Ri stops falling and holds steady, repairing should clear."""
    analysis = _default_analysis()
    # First a decline, then a long steady plateau at the last declined value.
    decline = 300e6 * (0.97 ** np.arange(20))
    ri = np.concatenate([decline, np.full(20, decline[-1])])
    times = np.arange(0, len(ri) * 0.5, 0.5)
    ra = np.full(len(ri), 80e6)
    analysis.process_measurements(_measurements(times, ra, ri))
    assert not analysis.is_repairing()


def test_collapsing_input_resistance_is_cell_loss():
    """Ri collapsing below the loss floor (and staying there) means the cell is gone."""
    analysis = _default_analysis()
    # Drop quickly to 20 MOhm then hold there for ~2 repair time constants.
    ri = np.concatenate([np.linspace(300e6, 20e6, 20), np.full(40, 20e6)])
    times = np.arange(0, len(ri) * 0.5, 0.5)
    ra = np.full(len(ri), 80e6)
    analysis.process_measurements(_measurements(times, ra, ri))
    assert analysis.cell_lost()


def test_brief_low_input_resistance_does_not_immediately_lose():
    """A low Ri reading on entry must not trip loss before one repair tau of data has accrued."""
    analysis = _default_analysis(repair_tau=10.0)
    # Ri sits below the loss floor, but only a few seconds of data (< repair_tau) so far.
    times = np.arange(0, 5, 0.5)  # 0..4.5s, well under the 10s repair tau
    ra = np.full(len(times), 80e6)
    ri = np.full(len(times), 20e6)
    analysis.process_measurements(_measurements(times, ra, ri))
    assert not analysis.cell_lost()


def test_recovery_is_blocked_while_cell_is_lost():
    """Ra dropping back down must not count as recovery if Ri has collapsed (cell lost wins)."""
    analysis = _default_analysis(repair_tau=10.0)
    times = np.arange(0, 20, 0.5)  # long enough to pass the loss delay
    ra = np.full(len(times), 10e6)  # below the recovered threshold
    ri = np.full(len(times), 20e6)  # below the loss floor
    analysis.process_measurements(_measurements(times, ra, ri))
    assert analysis.cell_lost()
    assert not analysis.access_recovered()


def test_process_test_pulses_reads_ra_and_ri():
    analysis = _default_analysis()
    tps = [
        _FakeTestPulse(0.0, 40e6, 300e6),
        _FakeTestPulse(0.5, 35e6, 290e6),
    ]
    result = analysis.process_test_pulses(tps)
    assert result["access_resistance"][0] == pytest.approx(40e6)
    assert result["input_resistance"][1] == pytest.approx(290e6)


def test_flags_default_false_before_any_data():
    analysis = _default_analysis()
    assert not analysis.access_recovered()
    assert not analysis.is_repairing()
    assert not analysis.cell_lost()
