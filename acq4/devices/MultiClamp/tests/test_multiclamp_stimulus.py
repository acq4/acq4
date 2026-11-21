"""MultiClamp records its command's neuroanalysis stimulus: the task GUI puts it in the command,
and MultiClampTask.getResult writes its saved state to Protocol['stimulus']. Test pulses pass
their SquarePulse through the same key."""
import json
import logging
from types import SimpleNamespace

import numpy as np
import pytest
from neuroanalysis import stimuli
from neuroanalysis.test_pulse import PatchClampTestPulse

from acq4.Manager import Task as ManagerTask
from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, readerThreads, runTask, waitUntil
from acq4.devices.MultiClamp.taskGUI import MultiClampTaskGui
from acq4.devices.MultiClamp.tests.test_multiclamp_result import FakeMultiClamp
from acq4.devices.PatchClamp import testpulse
from acq4.util import Qt

RATE = 10e3
NPTS = 1000


@pytest.fixture
def dm():
    dm = FakeManager()
    WaveDAQ(dm)
    FakeMultiClamp(dm, 'Clamp1')
    return dm


def _run(dm, clampCmd):
    """Run *clampCmd* for device 'Clamp1' through a real Manager.Task; return its result."""
    command = {'protocol': {'duration': NPTS / RATE}, 'DAQ': {'rate': RATE, 'numPts': NPTS}, 'Clamp1': clampCmd}
    return runTask(dm, command)[1]['Clamp1']


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='V', items=[
        stimuli.Offset(-65e-3),
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=-10e-3),
    ])


def test_getResult_records_saved_stimulus(dm):
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    cmd = {'mode': 'VC', 'command': wave, 'holding': -65e-3, 'stimulus': stim}
    result = _run(dm, cmd)

    np.testing.assert_allclose(result['Channel': 'command'].asarray(), wave)
    prot = result._info[-1]['Protocol']
    saved = prot['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == stim
    assert 'command' not in prot
    assert prot['mode'] == 'VC'

    # the live command is untouched
    assert cmd['stimulus'] is stim
    assert cmd['command'] is wave


def test_getResult_passes_saved_state_through(dm):
    state = _stimulus().save()
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS), 'stimulus': state}
    prot = _run(dm, cmd)._info[-1]['Protocol']
    assert prot['stimulus'] == state


def test_getResult_without_stimulus(dm):
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS)}
    prot = _run(dm, cmd)._info[-1]['Protocol']
    assert 'stimulus' not in prot


## test pulses


def _testPulseThread(dm):
    thread = testpulse.TestPulseThread.__new__(testpulse.TestPulseThread)
    thread._clampName = 'Clamp1'
    thread._daqName = 'DAQ'
    thread._manager = SimpleNamespace(createTask=lambda cmd: ManagerTask(dm, cmd))
    thread._clampDev = dm.getDevice('Clamp1')
    thread._params = {'postProcessing': None, 'sampleRate': 100e3, 'downsample': 1,
                      'vcPreDuration': 5e-3, 'vcPulseDuration': 10e-3, 'vcPostDuration': 5e-3,
                      'vcAmplitude': -10e-3, 'vcAverage': 2}
    return thread


def test_test_pulse_stimulus_end_to_end(dm):
    thread = _testPulseThread(dm)
    task = thread.createTask(thread.paramsForMode('VC'))
    square = task.command['Clamp1']['stimulus']
    assert isinstance(square, stimuli.SquarePulse)

    task.execute(block=False)
    waitUntil(task.isDone)
    tp = thread._makeTpResult(task)
    waitUntil(lambda: readerThreads() == [])
    assert isinstance(tp, PatchClampTestPulse)
    assert tp._stimulus is square  # the object, not its saved state

    result = task.getResult()['Clamp1']
    saved = result._info[-1]['Protocol']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == square
    assert task.command['Clamp1']['stimulus'] is square


## MultiClampTaskGui.generateTask


class _DaqUi(Qt.QObject):
    sigChanged = Qt.Signal(object)

    def currentState(self):
        return {'rate': RATE, 'numPts': NPTS}


class _TaskRunner(Qt.QObject):
    sigTaskSequenceStarted = Qt.Signal(object)
    sigTaskStarted = Qt.Signal(object)
    sigTaskFinished = Qt.Signal()

    def __init__(self):
        Qt.QObject.__init__(self)
        self.daqUi = _DaqUi()

    def getDevice(self, name):
        return self.daqUi


class _GuiClamp(Qt.QObject):
    sigStateChanged = Qt.Signal(object)
    sigHoldingChanged = Qt.Signal(object, object)
    logger = logging.getLogger(__name__)

    def name(self):
        return 'Clamp1'

    def getDAQName(self, ch):
        return 'DAQ'

    def listSignals(self, mode):
        return (['MembraneCurrent'], ['MembranePotential']) if mode == 'VC' else (['MembranePotential'], ['MembraneCurrent'])

    def getLastState(self, mode=None):
        holding = -65e-3 if mode == 'VC' else 0.0
        return {'holding': holding, 'primaryGain': 1, 'secondaryGain': 1,
                'primarySignal': self.listSignals(mode)[0][0], 'secondarySignal': self.listSignals(mode)[1][0]}


@pytest.fixture
def clampGui(qtbot):
    runner = _TaskRunner()
    dev = _GuiClamp()
    gui = MultiClampTaskGui(dev, runner)
    qtbot.addWidget(gui)
    gui._refs = (runner, dev)
    gui.setMode('VC')
    yield gui
    gui.quit()


def _addPulse(gen):
    gen.stimParams.addNew('Pulse')
    pulse = gen.stimParams.children()[-1]
    pulse['amplitude'] = -10e-3
    amp = pulse.param('amplitude')
    amp['sequence'] = 'list'
    amp['list'] = '-10e-3, -20e-3'
    return pulse


def test_generateTask_simple_mode(clampGui):
    gen = clampGui.ui.waveGeneratorWidget
    _addPulse(gen)
    for params, amp in [({}, -10e-3), ({'Pulse_amplitude': 1}, -20e-3)]:
        task = clampGui.generateTask(params)
        stim = task['stimulus']
        assert stim is gen.getStimulus(params)
        assert stim.units == 'V'
        assert [type(i) for i in stim.items] == [stimuli.Offset, stimuli.SquarePulse]
        assert stim.items[0].amplitude == -65e-3
        assert stim.items[1].amplitude == amp
        np.testing.assert_array_equal(stim.eval(n_pts=NPTS, sample_rate=RATE).data, task['command'])


def test_generateTask_advanced_mode(clampGui):
    gen = clampGui.ui.waveGeneratorWidget
    _addPulse(gen)
    gen.forceAdvancedClicked()
    task = clampGui.generateTask()
    assert 'command' in task
    assert 'stimulus' not in task


def test_generateTask_i0_mode(clampGui):
    _addPulse(clampGui.ui.waveGeneratorWidget)
    clampGui.setMode('I=0')
    task = clampGui.generateTask()
    assert 'command' not in task
    assert 'stimulus' not in task
