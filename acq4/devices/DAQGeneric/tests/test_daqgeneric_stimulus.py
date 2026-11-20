"""DAQGeneric records each channel's neuroanalysis stimulus: task GUIs put it in the command,
and DAQGenericTask.getResult writes its saved state to Protocol[<channel>]['stimulus']."""
import json

import numpy as np
import pytest
from neuroanalysis import stimuli
from pyqtgraph import PlotWidget

from acq4.devices.DAQGeneric.DAQGeneric import DAQGenericTask, savedStimulus
from acq4.devices.DAQGeneric.DaqChannelGui import OutputChannelGui
from acq4.util import Qt

RATE = 10e3
NPTS = 1000


class _FakeDaqTask:
    def getData(self, channel):
        return {'data': np.zeros(NPTS), 'info': {'rate': RATE, 'numPts': NPTS, 'startTime': 0.0}}


class _IdentityMapping:
    def mapFromDaq(self, ch, data):
        return data


class _FakeDev:
    _DGConfig = {
        'command': {'type': 'ao', 'channel': ('DAQ', '/Dev1/ao0'), 'units': 'V'},
        'primary': {'type': 'ai', 'channel': ('DAQ', '/Dev1/ai0'), 'units': 'A'},
    }

    def getChanUnits(self, ch):
        return self._DGConfig[ch]['units']


def _taskWithCommand(cmd):
    """A DAQGenericTask past configure/execute, with just what getResult reads."""
    task = DAQGenericTask.__new__(DAQGenericTask)
    task.dev = _FakeDev()
    task._DAQCmd = cmd
    task.bufferedChannels = list(cmd)
    task.daqTasks = {ch: _FakeDaqTask() for ch in cmd}
    task.mapping = _IdentityMapping()
    task.holdingVals = {'command': -60e-3}
    return task


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='V', items=[
        stimuli.Offset(-60e-3),
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=10e-3),
    ])


def test_getResult_records_saved_stimulus():
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    chCmd = {'command': wave, 'holding': -60e-3, 'stimulus': stim, 'lowLevelConf': {'x': 1}}
    cmd = {'command': chCmd, 'primary': {'record': True}}
    result = _taskWithCommand(cmd).getResult()

    prot = result._info[-1]['Protocol']
    saved = prot['command']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == stim
    assert 'command' not in prot['command']
    assert 'lowLevelConf' not in prot['command']
    assert prot['command']['holding'] == -60e-3
    assert prot['primary'] == {'record': True}

    # the live command is untouched
    assert chCmd['stimulus'] is stim
    assert chCmd['command'] is wave
    assert chCmd['lowLevelConf'] == {'x': 1}
    assert set(cmd) == {'command', 'primary'}


def test_getResult_repeatable():
    cmd = {'command': {'command': np.zeros(NPTS), 'stimulus': _stimulus()}}
    task = _taskWithCommand(cmd)
    first = task.getResult()._info[-1]['Protocol']
    second = task.getResult()._info[-1]['Protocol']
    assert first == second


def test_getResult_without_stimulus():
    cmd = {'command': {'command': np.zeros(NPTS)}}
    prot = _taskWithCommand(cmd).getResult()._info[-1]['Protocol']
    assert prot == {'command': {}}


def test_savedStimulus_passes_dicts_and_none():
    state = _stimulus().save()
    assert savedStimulus(state) is state
    assert savedStimulus(None) is None


def test_saved_stimulus_survives_metaarray_file(tmp_path):
    stim = _stimulus()
    cmd = {'command': {'command': np.zeros(NPTS), 'stimulus': stim}}
    result = _taskWithCommand(cmd).getResult()
    fn = str(tmp_path / 'result.ma')
    result.write(fn)
    from MetaArray import MetaArray
    loaded = MetaArray(file=fn)
    assert stimuli.Stimulus.load(loaded._info[-1]['Protocol']['command']['stimulus']) == stim


## OutputChannelGui.generateTask


class _ParentGui(Qt.QWidget):
    holding = -60e-3

    def getChanHolding(self, chan):
        return self.holding


class _DaqUi(Qt.QObject):
    sigChanged = Qt.Signal(object)

    def currentState(self):
        return {'rate': RATE, 'numPts': NPTS}


class _TaskRunner:
    def __init__(self):
        self.daqUi = _DaqUi()

    def getDevice(self, name):
        return self.daqUi


class _GuiDev(Qt.QObject):
    sigHoldingChanged = Qt.Signal(object, object)

    def getDAQName(self, ch):
        return 'DAQ'

    def name(self):
        return 'DAQGenericDev'


@pytest.fixture
def channelGui(qtbot):
    parent = _ParentGui()
    qtbot.addWidget(parent)
    runner = _TaskRunner()
    dev = _GuiDev()
    plot = PlotWidget()  # closed by gui.quit()
    gui = OutputChannelGui(parent, 'command', {'type': 'ao', 'units': 'V'}, plot, dev, runner)
    gui._refs = (parent, runner, dev)
    yield gui
    gui.quit()


def _addPulse(gen):
    gen.stimParams.addNew('Pulse')
    pulse = gen.stimParams.children()[-1]
    pulse['amplitude'] = 10e-3
    amp = pulse.param('amplitude')
    amp['sequence'] = 'list'
    amp['list'] = '10e-3, 20e-3'
    return pulse


def test_generateTask_simple_mode(channelGui):
    gen = channelGui.ui.waveGeneratorWidget
    _addPulse(gen)
    assert channelGui.ui.functionCheck.isChecked()

    for params, amp in [({}, 10e-3), ({'Pulse_amplitude': 1}, 20e-3)]:
        prot = channelGui.generateTask(params)
        stim = prot['stimulus']
        assert isinstance(stim, stimuli.Stimulus)
        assert stim is gen.getStimulus(params)
        assert [type(i) for i in stim.items] == [stimuli.Offset, stimuli.SquarePulse]
        assert stim.items[0].amplitude == -60e-3
        assert stim.items[1].amplitude == amp
        np.testing.assert_array_equal(stim.eval(n_pts=NPTS, sample_rate=RATE).data, prot['command'])


def test_generateTask_offset_follows_holding(channelGui):
    _addPulse(channelGui.ui.waveGeneratorWidget)
    channelGui.taskGui().holding = -70e-3
    prot = channelGui.generateTask()
    assert prot['stimulus'].items[0].amplitude == -70e-3
    assert prot['command'][0] == -70e-3


def test_generateTask_advanced_mode(channelGui):
    gen = channelGui.ui.waveGeneratorWidget
    _addPulse(gen)
    gen.forceAdvancedClicked()
    prot = channelGui.generateTask()
    assert 'command' in prot
    assert 'stimulus' not in prot


def test_generateTask_function_disabled(channelGui):
    _addPulse(channelGui.ui.waveGeneratorWidget)
    channelGui.ui.functionCheck.setChecked(False)
    prot = channelGui.generateTask()
    assert 'command' not in prot
    assert 'stimulus' not in prot
