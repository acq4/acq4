"""Manager.Task.stopEarly() with a MultiClampTask on the mock NI-DAQ driver."""

import numpy as np
import pytest

from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    FakeManager,
    PartialRecorder,
    WaveDAQ,
    assertSameResult,
    checkTruncatedPartials,
    runTaskStoppedEarly,
    withoutEarlyStopInfo,
)
from acq4.devices.MultiClamp.tests.legacy_multiclamp_result import legacyGetResult
from acq4.devices.MultiClamp.tests.test_multiclamp_result import AI0, AI1, FakeMultiClamp, wave

RATE = 50_000.0
NPTS = 50_000  # 1 s; the tests stop it early
INTERVAL = 0.02


class _HoldingRecorderClamp(FakeMultiClamp):
    def __init__(self, dm):
        FakeMultiClamp.__init__(self, dm)
        self.holdingResets = 0

    def setHolding(self, mode=None, value=None):
        if mode is None and value is None:
            self.holdingResets += 1
        FakeMultiClamp.setHolding(self, mode, value)


@pytest.fixture
def rig():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: wave(0.0), AI1: wave(2.0)})
    clamp = _HoldingRecorderClamp(dm)
    return dm, clamp


def command(mode, daqCmd=None, **clampCmd):
    return {
        'protocol': {'duration': NPTS / RATE, 'updateInterval': INTERVAL},
        'DAQ': {'rate': RATE, 'numPts': NPTS, **(daqCmd or {})},
        'Clamp1': {'mode': mode, **clampCmd},
    }


CASES = {
    'VC': dict(mode='VC', command=-0.065 + 0.01 * ((np.arange(NPTS) // 3000) % 2), holding=-0.065),
    'IC_downsample4': dict(
        mode='IC', daqCmd={'downsample': 4}, command=100e-12 * ((np.arange(NPTS) // 3000) % 2)
    ),
    'I0_noCommand': dict(mode='I=0', recordSecondary=False),
}


@pytest.mark.parametrize('name', list(CASES))
def test_stop_early_truncates_clamp_result(rig, name):
    dm, clamp = rig
    case = dict(CASES[name])
    ds = case.get('daqCmd', {}).get('downsample', 1)
    rec = PartialRecorder('Clamp1')
    task, truncated, result = runTaskStoppedEarly(dm, command(**case), rec)
    assert truncated is True
    mcTask = task.tasks['Clamp1']
    final = result['Clamp1']
    cols = [c['name'] for c in final._info[0]['cols']]
    assert ('command' in cols) == ('command' in case)

    n = result['protocol']['numPtsAcquired']['DAQ']
    assert n % ds == 0 and 0 < n < NPTS
    m = n // ds
    assert final.shape == (len(cols), m) and len(final.xvals('Time')) == m
    top = final._info[-1]
    assert (
        top['stoppedEarly'] is True
        and top['numPtsAcquired'] == n
        and top['numPtsRequested'] == NPTS
    )
    for ch in cols:
        assert top['DAQ'][ch]['numPts'] == top['DAQ'][ch]['validSamples'] == m
    assert top['ClampState'] is mcTask.state
    assert clamp.holdingResets >= 1

    checkTruncatedPartials(rec, final, NPTS // ds, outputs=('command',))
    assertSameResult(withoutEarlyStopInfo(final), legacyGetResult(mcTask), buffered=cols)
