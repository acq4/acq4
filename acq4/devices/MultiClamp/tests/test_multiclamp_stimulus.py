"""MultiClamp records its command's neuroanalysis stimulus: the task GUI puts it in the command,
and MultiClampTask.getResult writes its saved state to Protocol['stimulus']. Test pulses pass
their SquarePulse through the same key."""
import json
import logging

import numpy as np
import pytest
from neuroanalysis import stimuli
from neuroanalysis.test_pulse import PatchClampTestPulse

from acq4.devices.MultiClamp.multiclamp import MultiClampTask
from acq4.devices.MultiClamp.taskGUI import MultiClampTaskGui
from acq4.devices.PatchClamp import testpulse
from acq4.util import Qt

RATE = 10e3
NPTS = 1000
CHANNELS = {
    'primaryChannel': {'device': 'DAQ', 'channel': '/Dev1/ai0', 'type': 'ai'},
    'secondaryChannel': {'device': 'DAQ', 'channel': '/Dev1/ai1', 'type': 'ai'},
    'commandChannel': {'device': 'DAQ', 'channel': '/Dev1/ao0', 'type': 'ao'},
}


class _FakeDaqTask:
    """Returns the written command on the command channel and zeros elsewhere."""
    def __init__(self, nPts, rate, command=None):
        self.nPts, self.rate, self.command = nPts, rate, command

    def getData(self, channel):
        data = self.command if channel == CHANNELS['commandChannel']['channel'] else np.zeros(self.nPts)
        return {'data': np.array(data, dtype=float),
                'info': {'rate': self.rate, 'numPts': self.nPts, 'startTime': 1000.0}}


class _FakeClamp:
    config = CHANNELS


def _executedTask(cmd, nPts=NPTS, rate=RATE):
    """A MultiClampTask built from *cmd* as Manager.Task does, with just what getResult reads."""
    task = MultiClampTask(_FakeClamp(), cmd, None)
    task.state = {'extCmdScale': 1.0, 'primaryScaleFactor': 1.0, 'primaryUnits': 'A',
                  'secondaryScaleFactor': 1.0, 'secondaryUnits': 'V'}
    task.holdingVal = cmd.get('holding', 0.0)
    daq = _FakeDaqTask(nPts, rate, cmd.get('command'))
    task.daqTasks = {ch: daq for ch in task.getUsedChannels()}
    return task


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='V', items=[
        stimuli.Offset(-65e-3),
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=-10e-3),
    ])


def test_getResult_records_saved_stimulus():
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    cmd = {'mode': 'VC', 'command': wave, 'holding': -65e-3, 'stimulus': stim}
    result = _executedTask(cmd).getResult()

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


def test_getResult_passes_saved_state_through():
    state = _stimulus().save()
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS), 'stimulus': state}
    prot = _executedTask(cmd).getResult()._info[-1]['Protocol']
    assert prot['stimulus'] == state


def test_getResult_without_stimulus():
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS)}
    prot = _executedTask(cmd).getResult()._info[-1]['Protocol']
    assert 'stimulus' not in prot


## test pulses


class _TestPulseClamp:
    def getHolding(self, mode):
        return -70e-3


class _TaskFromCommand:
    """Stands in for Manager.Task: hands each device its slice of the command, as Task does."""
    def __init__(self, cmd):
        self.command = cmd
        self.clampTask = _executedTask(cmd['Clamp1'], nPts=cmd['DAQ']['numPts'], rate=cmd['DAQ']['rate'])

    def getResult(self):
        return {'Clamp1': self.clampTask.getResult()}


class _Manager:
    def createTask(self, cmd):
        return _TaskFromCommand(cmd)


def _testPulseThread():
    thread = testpulse.TestPulseThread.__new__(testpulse.TestPulseThread)
    thread._clampName = 'Clamp1'
    thread._daqName = 'DAQ'
    thread._manager = _Manager()
    thread._clampDev = _TestPulseClamp()
    thread._params = {'postProcessing': None, 'sampleRate': 100e3, 'downsample': 1,
                      'vcPreDuration': 5e-3, 'vcPulseDuration': 10e-3, 'vcPostDuration': 5e-3,
                      'vcAmplitude': -10e-3, 'vcAverage': 2}
    return thread


def test_test_pulse_stimulus_end_to_end():
    thread = _testPulseThread()
    task = thread.createTask(thread.paramsForMode('VC'))
    square = task.command['Clamp1']['stimulus']
    assert isinstance(square, stimuli.SquarePulse)

    tp = thread._makeTpResult(task)
    assert isinstance(tp, PatchClampTestPulse)
    assert tp._stimulus is square  # the object, not its saved state

    result = task.clampTask.getResult()
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
