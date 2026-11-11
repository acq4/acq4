"""DAQGeneric records each channel's neuroanalysis stimulus: task GUIs put it in the command,
and DAQGenericTask.getResult writes its saved state to Protocol[<channel>]['stimulus']."""
import json

import numpy as np
import pytest
from MetaArray import MetaArray
from neuroanalysis import stimuli
from pyqtgraph import PlotWidget

from acq4.devices.DAQGeneric import DAQGeneric
from acq4.devices.DAQGeneric.DAQGeneric import savedStimulus
from acq4.devices.DAQGeneric.DaqChannelGui import OutputChannelGui
from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, runTask
from acq4.util import Qt

RATE = 10e3
NPTS = 1000
AO, AI0 = '/Dev1/ao0', '/Dev1/ai0'
CHANNELS = {
    'command': {'device': 'DAQ', 'channel': AO, 'type': 'ao', 'units': 'V'},
    'primary': {'device': 'DAQ', 'channel': AI0, 'type': 'ai', 'units': 'A'},
}


@pytest.fixture
def dm():
    dm = FakeManager()
    WaveDAQ(dm)
    DAQGeneric(dm, {'channels': {k: dict(v) for k, v in CHANNELS.items()}}, 'Gen')
    return dm


def _run(dm, genCmd):
    """Run *genCmd* for device 'Gen' through a real Manager.Task; return (DAQGenericTask, result)."""
    command = {'protocol': {'duration': NPTS / RATE}, 'DAQ': {'rate': RATE, 'numPts': NPTS}, 'Gen': genCmd}
    task, result = runTask(dm, command)
    return task.tasks['Gen'], result['Gen']


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='V', items=[
        stimuli.Offset(-60e-3),
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=10e-3),
    ])


def test_getResult_records_saved_stimulus(dm):
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    written = []
    lowLevelConf = {'mockFunc': lambda data, dt: written.append(data)}
    chCmd = {'command': wave, 'holding': -60e-3, 'stimulus': stim, 'lowLevelConf': lowLevelConf}
    cmd = {'command': chCmd, 'primary': {'record': True}}
    _, result = _run(dm, cmd)

    assert len(written) == 1  # lowLevelConf reached the driver
    np.testing.assert_allclose(result['Channel': 'command'].asarray(), wave)
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
    assert chCmd['lowLevelConf'] is lowLevelConf and list(lowLevelConf) == ['mockFunc']
    assert set(cmd) == {'command', 'primary'}


def test_getResult_repeatable(dm):
    cmd = {'command': {'command': np.zeros(NPTS), 'stimulus': _stimulus()}}
    genTask, result = _run(dm, cmd)
    first = result._info[-1]['Protocol']
    assert genTask.getResult()._info[-1]['Protocol'] == first
    # the same command run again, as a repeated task sequence does
    _, again = _run(dm, cmd)
    assert again._info[-1]['Protocol'] == first
    assert 'stimulus' in first['command']


def test_getResult_without_stimulus(dm):
    cmd = {'command': {'command': np.zeros(NPTS)}}
    _, result = _run(dm, cmd)
    assert result._info[-1]['Protocol'] == {'command': {}}


def test_savedStimulus_passes_dicts_and_none():
    state = _stimulus().save()
    assert savedStimulus(state) is state
    assert savedStimulus(None) is None


def test_saved_stimulus_survives_metaarray_file(dm, tmp_path):
    stim = _stimulus()
    cmd = {'command': {'command': np.zeros(NPTS), 'stimulus': stim}}
    _, result = _run(dm, cmd)
    fn = str(tmp_path / 'result.ma')
    result.write(fn)
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
