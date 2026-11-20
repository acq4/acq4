"""Laser records its power waveform's neuroanalysis stimulus: the task GUI puts it in the command,
and LaserTask.getResult writes its saved state to Protocol['power']['stimulus']."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from MetaArray import MetaArray, axis
from neuroanalysis import stimuli

from acq4.devices.DAQGeneric import DAQGenericTask
from acq4.devices.Laser.Laser import LaserTask
from acq4.devices.Laser.LaserTaskGui import LaserTaskGui
from acq4.util.generator.StimGenerator import StimGenerator

RATE = 10e3
NPTS = 1000


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='W', items=[
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=5e-3),
    ])


def _daqResult():
    info = [axis(name='Channel', cols=[{'name': 'shutter'}]), axis(name='Time', values=np.arange(NPTS) / RATE),
            {'DAQ': {'shutter': {'downsampling': 1}}, 'Protocol': {'shutter': {}}}]
    return MetaArray(np.zeros((1, NPTS)), info=info)


def _executedTask(cmd):
    task = LaserTask.__new__(LaserTask)
    task.cmd = cmd
    task.dev = SimpleNamespace(lastResult=None)
    task.currentPower = task.expectedPower = 5e-3
    return task


def test_getResult_records_saved_stimulus(monkeypatch):
    monkeypatch.setattr(DAQGenericTask, 'getResult', lambda self: _daqResult())
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    cmd = {'powerWaveform': wave, 'ignorePowerWaveform': True, 'stimulus': stim, 'shutterMode': 'auto'}
    result = _executedTask(cmd).getResult()

    prot = result._info[-1]['Protocol']
    saved = prot['power']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == stim
    assert prot['shutter'] == {}
    assert cmd['stimulus'] is stim
    np.testing.assert_array_equal(result['Channel': 'power'], wave)


def test_getResult_without_stimulus(monkeypatch):
    monkeypatch.setattr(DAQGenericTask, 'getResult', lambda self: _daqResult())
    cmd = {'powerWaveform': np.zeros(NPTS), 'shutterMode': 'auto'}
    prot = _executedTask(cmd).getResult()._info[-1]['Protocol']
    assert 'power' not in prot


@pytest.fixture
def taskGui(qtbot):
    gen = StimGenerator()
    qtbot.addWidget(gen)
    gen.setMeta('y', units='W')

    def getSingleWave(params=None):
        gen.setOffset(0)
        return gen.getSingle(RATE, NPTS, params)

    return SimpleNamespace(
        powerFnGenerator=gen,
        powerWidget=SimpleNamespace(rate=RATE, getSingleWave=getSingleWave),
        getChannelCmds=lambda wave, rate: {'shutter': (wave != 0).astype(np.byte)},
    )


def _addPulse(gen):
    gen.stimParams.addNew('Pulse')
    pulse = gen.stimParams.children()[-1]
    pulse['amplitude'] = 5e-3
    amp = pulse.param('amplitude')
    amp['sequence'] = 'list'
    amp['list'] = '5e-3, 10e-3'


def test_generateTask_simple_mode(taskGui):
    gen = taskGui.powerFnGenerator
    _addPulse(gen)
    for params, amp in [({}, 5e-3), ({'power.Pulse_amplitude': 1}, 10e-3)]:
        cmd = LaserTaskGui.generateTask(taskGui, dict(params))
        stim = cmd['stimulus']
        assert stim.units == 'W'
        assert stim.items[0].amplitude == amp
        np.testing.assert_array_equal(stim.eval(n_pts=NPTS, sample_rate=RATE).data, cmd['powerWaveform'])
        assert 'command' in cmd['shutter']


def test_generateTask_advanced_mode(taskGui):
    gen = taskGui.powerFnGenerator
    _addPulse(gen)
    gen.forceAdvancedClicked()
    cmd = LaserTaskGui.generateTask(taskGui, {})
    assert 'powerWaveform' in cmd
    assert 'stimulus' not in cmd
