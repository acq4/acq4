"""Tests for TestPulseThread.updateAutoBias current limits and resistance rejection."""
from types import SimpleNamespace

import numpy as np
import pytest

from acq4.devices.PatchClamp import testpulse


class _FakeClamp:
    def __init__(self, icHolding=0.0, vcHolding=-70e-3):
        self.holding = {'IC': icHolding, 'VC': vcHolding}
        self.writes = []

    def getHolding(self, mode):
        return self.holding[mode.upper()]

    def setHolding(self, mode, value):
        self.writes.append((mode.upper(), float(value)))


def _updateAutoBias(mode, clamp=None, params=None, **analysis):
    """Run updateAutoBias on a bare thread object; return the holding writes it made."""
    thread = testpulse.TestPulseThread.__new__(testpulse.TestPulseThread)
    thread._params = {
        'autoBiasTarget': -70e-3,
        'autoBiasFollowRate': 0.5,
        'autoBiasMaxCurrent': 2e-9,
        'autoBiasMinResistance': 50e6,
        'autoBiasVCCarryover': 1.0,
        **(params or {}),
    }
    thread._clampDev = clamp = clamp or _FakeClamp()
    tp = SimpleNamespace(analysis=analysis, recording=SimpleNamespace(clamp_mode=mode))
    thread.updateAutoBias(tp)
    return clamp.writes


@pytest.mark.parametrize('rss', [-84e6, np.nan, 0.0, 10e6, 49.9e6])
@pytest.mark.parametrize('mode', ['ic', 'vc'])
def test_rejects_low_or_invalid_resistance(mode, rss):
    writes = _updateAutoBias(mode, steady_state_resistance=rss, baseline_potential=-87e-3, baseline_current=-7e-9)
    assert writes == []


def test_ic_proportional_update():
    clamp = _FakeClamp(icHolding=-10e-12)
    writes = _updateAutoBias('ic', clamp, steady_state_resistance=200e6, baseline_potential=-65e-3)
    expected = -10e-12 + (-70e-3 - -65e-3) / 200e6 * 0.5
    assert writes == [('IC', pytest.approx(expected))]


@pytest.mark.parametrize('vm, limit', [(-0.5, 2e-9), (0.5, -2e-9)])
def test_ic_update_is_limited(vm, limit):
    writes = _updateAutoBias('ic', steady_state_resistance=60e6, baseline_potential=vm)
    assert writes == [('IC', pytest.approx(limit))]


def test_ic_target_defaults_to_vc_holding():
    clamp = _FakeClamp(icHolding=0.0, vcHolding=-60e-3)
    writes = _updateAutoBias(
        'ic', clamp, params={'autoBiasTarget': None, 'autoBiasFollowRate': 1.0},
        steady_state_resistance=100e6, baseline_potential=-70e-3,
    )
    assert writes == [('IC', pytest.approx(10e-3 / 100e6))]


def test_vc_carryover_sets_ic_holding():
    writes = _updateAutoBias('vc', steady_state_resistance=500e6, baseline_current=-50e-12)
    assert writes == [('IC', pytest.approx(-50e-12))]


@pytest.mark.parametrize('current, limit', [(-7e-9, -2e-9), (7e-9, 2e-9)])
def test_vc_carryover_is_limited(current, limit):
    writes = _updateAutoBias('vc', steady_state_resistance=500e6, baseline_current=current)
    assert writes == [('IC', pytest.approx(limit))]
