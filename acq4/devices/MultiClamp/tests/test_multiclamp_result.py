"""MultiClampTask results through a real Manager.Task and NiDAQ on the mock driver, against the original getResult."""
import logging

import numpy as np
import pytest

from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    FakeManager, WaveDAQ, PartialRecorder, assertSameResult, checkPartials, runTask,
)
from acq4.devices.MultiClamp.multiclamp import MultiClampTask
from acq4.devices.MultiClamp.tests.legacy_multiclamp_result import legacyGetResult
from acq4.util.partial_results import TaskResultArray

RATE = 50_000.0
NPTS = 12_000  # 0.24 s
INTERVAL = 0.02
AI0, AI1, AO = '/Dev1/ai0', '/Dev1/ai1', '/Dev1/ao0'

STATES = {
    'VC': {'primaryScaleFactor': 2e-9, 'primaryUnits': 'A', 'secondaryScaleFactor': 0.1, 'secondaryUnits': 'V',
           'extCmdScale': 0.02},
    'IC': {'primaryScaleFactor': 0.1, 'primaryUnits': 'V', 'secondaryScaleFactor': 2.5e-9,
           'secondaryUnits': 'A', 'extCmdScale': 4e-10},
}
STATES['I=0'] = dict(STATES['IC'])


def wave(phase):
    def fn(n, rate):
        t = np.arange(n) / rate
        return 0.3 + 0.4 * np.sin(2 * np.pi * 25 * t + phase) + 0.01 * np.random.default_rng(n).standard_normal(n)
    return fn


class _FakeMC:
    def __init__(self):
        self.params = {}

    def setParam(self, name, value):
        self.params[name] = value

    def setParams(self, params):
        self.params.update(params)

    def getParams(self, names):
        return {name: float(i) for i, name in enumerate(names)}


class FakeMultiClamp:
    """The parts of MultiClamp that MultiClampTask uses."""

    def __init__(self, dm, name='Clamp1'):
        self._name = name
        self.logger = logging.getLogger(f'acq4.device.test.{name}')
        self.config = {
            'primaryChannel': {'device': 'DAQ', 'channel': AI0, 'type': 'ai'},
            'secondaryChannel': {'device': 'DAQ', 'channel': AI1, 'type': 'ai', 'mode': 'nrse'},
            'commandChannel': {'device': 'DAQ', 'channel': AO, 'type': 'ao'},
        }
        self.mc = _FakeMC()
        self.mode = 'VC'
        self.holding = {'VC': -0.065, 'IC': 0.0, 'I=0': 0.0}
        dm.devices[name] = self

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return MultiClampTask(self, cmd, parentTask)

    def getDAQName(self, channel):
        return self.config[f'{channel}Channel']['device']

    def setMode(self, mode):
        self.mode = mode

    def setHolding(self, mode=None, value=None):
        if mode is not None and value is not None:
            self.holding[mode] = value

    def getHolding(self, mode):
        return self.holding[mode]

    def setPrimarySignal(self, sig):
        pass

    def setSecondarySignal(self, sig):
        pass

    def getLastState(self):
        return {'mode': self.mode, **STATES[self.mode]}


@pytest.fixture
def rig():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: wave(0.0), AI1: wave(2.0)})
    clamp = FakeMultiClamp(dm)
    return dm, clamp


def command(mode='VC', daqCmd=None, interval=INTERVAL, **clampCmd):
    protocol = {'duration': NPTS / RATE}
    if interval is not None:
        protocol['updateInterval'] = interval
    clamp = {'mode': mode, **clampCmd}
    return {'protocol': protocol, 'DAQ': {'rate': RATE, 'numPts': NPTS, **(daqCmd or {})}, 'Clamp1': clamp}


def vcCommand():
    return -0.065 + 0.01 * ((np.arange(NPTS) // 3000) % 2)


def icCommand():
    return 100e-12 * ((np.arange(NPTS) // 3000) % 2)


CASES = {
    'VC': dict(mode='VC', command=vcCommand(), holding=-0.065),
    'VC_downsample10_recordState': dict(mode='VC', daqCmd={'downsample': 10}, command=vcCommand(), recordState=True,
                                        primaryGain=2),
    'IC_downsample4': dict(mode='IC', daqCmd={'downsample': 4}, command=icCommand(), holding=0.0),
    'IC_noSecondary': dict(mode='IC', command=icCommand(), recordSecondary=False),
    'I0_primaryOnly': dict(mode='I=0', recordSecondary=False),
}


def expectedColumns(case):
    cols = ['primary']
    if case.get('recordSecondary', True):
        cols.append('secondary')
    if 'command' in case:
        cols.append('command')
    return cols


@pytest.mark.parametrize('name', list(CASES))
def test_partials_are_the_final_object_and_final_matches_original(rig, name):
    dm, clamp = rig
    case = dict(CASES[name])
    rec = PartialRecorder('Clamp1')
    task, result = runTask(dm, command(**case), rec)
    mcTask = task.tasks['Clamp1']
    final = result['Clamp1']
    cols = expectedColumns(case)

    assert isinstance(final, TaskResultArray)
    assert [c['name'] for c in final._info[0]['cols']] == cols
    assert task.partialResultErrors == []
    checkPartials(rec, final, outputs=['command'] if 'command' in cols else ())
    assert mcTask.getResult() is final and mcTask.partialResult() is final
    assert set(mcTask.settleSpecs()) == {c for c in cols if c != 'command'}
    assert rec.calls[-1]['settled']['primary'] == final.shape[1]

    assertSameResult(final, legacyGetResult(mcTask), buffered=cols)
    assert final._info[-1]['ClampState'] is mcTask.state


@pytest.mark.parametrize('name', ['VC', 'IC_downsample4'])
def test_no_update_interval_is_inert_and_matches_original(rig, name):
    dm, clamp = rig
    case = dict(CASES[name])
    rec = PartialRecorder('Clamp1')
    task, result = runTask(dm, command(interval=None, **case), rec)
    mcTask = task.tasks['Clamp1']
    final = result['Clamp1']
    assert rec.calls == []
    assert final.isComplete() and mcTask.getResult() is final
    assertSameResult(final, legacyGetResult(mcTask), buffered=expectedColumns(case))


def test_partial_result_shows_the_primary_column_for_the_dock(rig):
    """The MultiClamp dock reads result['primary'], settlement()['primary'] and xvals('Time')."""
    dm, clamp = rig
    seen = []

    def handler(payload):
        res = payload['Clamp1']
        n = res.settlement()['primary']
        seen.append((n, res['primary'].view(np.ndarray)[:n].copy(), len(res.xvals('Time'))))

    task, result = runTask(dm, command(**CASES['VC']), handler)
    final = result['Clamp1']
    assert len(seen) >= 2
    primary = final['primary'].view(np.ndarray)
    for n, prefix, nTime in seen:
        assert nTime == NPTS
        assert np.array_equal(prefix, primary[:n])
