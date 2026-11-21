"""Results of DAQGenericTask subclasses (Laser, MockClamp) on the mock NiDAQ, against their original getResult."""
import threading

import numpy as np
import pytest

from MetaArray import MetaArray
from acq4.devices.DAQGeneric import DAQGeneric
from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    FakeManager, WaveDAQ, PartialRecorder, assertSameResult, checkPartials, runTask,
)
from acq4.devices.DAQGeneric.tests.legacy_subclass_results import legacyLaserGetResult, legacyMockClampGetResult
from acq4.devices.Laser.Laser import LaserTask
from acq4.devices.MockClamp.MockClamp import MockClampTask, ivModes
from acq4.util.partial_results import TaskResultArray

RATE = 50_000.0
NPTS = 10_000  # 0.2 s
INTERVAL = 0.02
AI0, AI1, AO, SHUTTER = '/Dev1/ai0', '/Dev1/ai1', '/Dev1/ao0', '/Dev1/port0/line3'


def wave(n, rate):
    t = np.arange(n) / rate
    return 0.2 + 0.3 * np.sin(2 * np.pi * 30 * t) + 0.01 * np.random.default_rng(n).standard_normal(n)


class FakeLaser(DAQGeneric):
    """DAQGeneric with the Laser methods LaserTask uses, and one DAQ-driven shutter."""

    def __init__(self, dm, name='Laser1'):
        config = {'shutter': {'device': 'DAQ', 'channel': SHUTTER, 'type': 'do'}}
        DAQGeneric.__init__(self, dm, {'shutter': dict(config['shutter']), 'power': {'type': 'ao', 'units': 'W'}},
                            name)
        self.config = config
        self.params = {'currentPower': 0.5, 'expectedPower': 0.55}
        self.lastResult = None

    def createTask(self, cmd, parentTask):
        return LaserTask(self, cmd, parentTask)

    def getDAQName(self, channel=None):
        if channel is None:
            return DAQGeneric.getDAQName(self, 'shutter'), 'shutter'
        return DAQGeneric.getDAQName(self, channel)

    def getParam(self, name):
        return self.params[name]

    def getChannelCmds(self, cmd, rate):
        waveform = cmd.get('switchWaveform', cmd.get('powerWaveform'))
        return {'shutter': (waveform > 0).astype(float)}


@pytest.fixture
def dm():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: wave, AI1: wave})
    DAQGeneric(dm, {'channels': {'P': {'device': 'DAQ', 'channel': AI1, 'type': 'ai', 'units': 'V'}}}, 'Probe')
    return dm


def pulses():
    return 0.8 * ((np.arange(NPTS) // 1000) % 2)


@pytest.mark.parametrize('laserCmd, ds, column', [
    ({'switchWaveform': pulses()}, 1, {'name': 'switch'}),
    ({'powerWaveform': pulses() * 1e-3}, 2, {'name': 'power', 'units': 'W'}),
])
def test_laser_appends_its_column_once(dm, laserCmd, ds, column):
    laser = FakeLaser(dm)
    rec = PartialRecorder('Probe')
    command = {
        'protocol': {'duration': NPTS / RATE, 'updateInterval': INTERVAL},
        'DAQ': {'rate': RATE, 'numPts': NPTS, 'downsample': ds},
        'Laser1': laserCmd,
        'Probe': {'P': {'record': True}},
    }
    task, result = runTask(dm, command, rec)
    laserTask = task.tasks['Laser1']
    final = result['Laser1']

    assert len(rec.calls) >= 2 and all('Laser1' not in call['keys'] for call in rec.calls)
    assert laserTask.partialResult() is None and laserTask.settleSpecs() == {}
    assert type(final) is MetaArray
    assert laser.lastResult is final

    written = []

    class _Dir:
        def writeFile(self, obj, name):
            written.append(obj)

    laserTask.storeResult(_Dir())  # calls getResult() again
    assert laserTask.getResult() is final and written == [final]
    assert final._info[0]['cols'] == [{'name': 'shutter', 'units': None}, column]
    assert final.shape == (2, NPTS // ds)
    assertSameResult(final, legacyLaserGetResult(laserTask), buffered=['shutter'])


class _FakeSimJob:
    def __init__(self, params):
        self.params = params
        self.resultThreads = []

    def result(self, timeout=None):
        self.resultThreads.append(threading.current_thread().name)
        data = self.params['data']
        return 1e-1 * data + 2e-2 * np.sin(np.arange(len(data)) / 50.0)


class _FakeSimulator:
    def __init__(self):
        self.jobs = []

    def run(self, params, _sync='sync'):
        assert _sync == 'async'
        self.jobs.append(_FakeSimJob(params))
        return self.jobs[-1]


class FakeMockClamp:
    """The parts of MockClamp that MockClampTask uses, with an in-process simulator."""

    def __init__(self, dm, name='Clamp1'):
        self._name = name
        self.daqDev = DAQGeneric(dm, {
            'command': {'device': 'DAQ', 'channel': AO, 'type': 'ao', 'units': 'V', 'scale': 50.0},
            'primary': {'device': 'DAQ', 'channel': AI0, 'type': 'ai', 'units': 'A', 'scale': 1e-9},
        }, f'{name}Daq')
        self.simulator = _FakeSimulator()
        self.mode = 'VC'
        self.holding = {'VC': -0.05, 'IC': 0.0}
        dm.devices[name] = self

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return MockClampTask(self, cmd, parentTask)

    def getHolding(self, mode):
        return self.holding[ivModes[mode]]

    def setMode(self, mode):
        self.mode = mode

    def getMode(self):
        return self.mode


@pytest.mark.parametrize('interval', [INTERVAL, None])
def test_mock_clamp_result_is_the_partial_object(dm, interval):
    clamp = FakeMockClamp(dm)
    rec = PartialRecorder('Clamp1')
    protocol = {'duration': NPTS / RATE}
    if interval is not None:
        protocol['updateInterval'] = interval
    command = {
        'protocol': protocol,
        'DAQ': {'rate': RATE, 'numPts': NPTS},
        'Clamp1': {'mode': 'VC', 'command': -0.05 + 0.01 * ((np.arange(NPTS) // 2000) % 2)},
    }
    task, result = runTask(dm, command, rec)
    clampTask = task.tasks['Clamp1']
    final = result['Clamp1']

    assert isinstance(final, TaskResultArray)
    assert clampTask.getResult() is final
    assert final._info[-1]['ClampState'] is clampTask.ampState
    assert final._info[-1]['startTime'] == final._info[-1]['DAQ']['command']['startTime'] is not None
    if interval is None:
        assert rec.calls == []
    else:
        checkPartials(rec, final, outputs=['command'])
    assert [len(job.resultThreads) for job in clamp.simulator.jobs] == [1]
    assertSameResult(final, legacyMockClampGetResult(clampTask), buffered=['command', 'primary'])


def test_axopatch200_result_is_the_partial_object(qtbot, dm):
    from acq4.devices.AxoPatch200.AxoPatch200 import AxoPatch200
    from acq4.devices.DAQGeneric.tests.legacy_daqgeneric_result import legacyGetResult

    dm.getDevice('DAQ').waves['/Dev1/ai5'] = wave
    tel = {'device': 'DAQ', 'type': 'ai'}
    axo = AxoPatch200(dm, {
        'version': '200B',
        'ModeChannel': dict(tel, channel='/Dev1/ai13'),
        'GainChannel': dict(tel, channel='/Dev1/ai14'),
        'LPFChannel': dict(tel, channel='/Dev1/ai15'),
        'Command': {'device': 'DAQ', 'channel': AO, 'type': 'ao'},
        'ScaledSignal': {'device': 'DAQ', 'channel': '/Dev1/ai5', 'type': 'ai'},
    }, 'Axo')
    rec = PartialRecorder('Axo')
    command = {
        'protocol': {'duration': NPTS / RATE, 'updateInterval': INTERVAL},
        'DAQ': {'rate': RATE, 'numPts': NPTS},
        'Axo': {'command': 1e-10 * ((np.arange(NPTS) // 2000) % 2)},
    }
    task, result = runTask(dm, command, rec)
    axoTask = task.tasks['Axo']
    final = result['Axo']

    assert isinstance(final, TaskResultArray)
    checkPartials(rec, final, outputs=['command'])
    assertSameResult(final, legacyGetResult(axoTask), buffered=['primary', 'command'])

    written = []

    class _Dir:
        def writeFile(self, obj, name):
            written.append(obj)

    axoTask.storeResult(_Dir())
    assert written == [final] and final._info[-1]['ClampState'] == axoTask.ampState
    axo.modeDialog.close()
