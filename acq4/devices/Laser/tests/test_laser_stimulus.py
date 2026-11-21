"""Laser records its power waveform's neuroanalysis stimulus: the task GUI puts it in the command,
and LaserTask.getResult writes its saved state to Protocol['power']['stimulus']."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from neuroanalysis import stimuli

from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, runTask
from acq4.devices.DAQGeneric.tests.test_daqgeneric_subclass_results import FakeLaser
from acq4.devices.Laser.LaserTaskGui import LaserTaskGui
from acq4.util.generator.StimGenerator import StimGenerator

RATE = 10e3
NPTS = 1000


def _stimulus():
    return stimuli.Stimulus(description='StimGenerator', units='W', items=[
        stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=5e-3),
    ])


def _run(laserCmd):
    """Run *laserCmd* for a FakeLaser 'Laser1' through a real Manager.Task; return its result."""
    dm = FakeManager()
    WaveDAQ(dm)
    FakeLaser(dm)
    command = {'protocol': {'duration': NPTS / RATE}, 'DAQ': {'rate': RATE, 'numPts': NPTS}, 'Laser1': laserCmd}
    return runTask(dm, command)[1]['Laser1']


def _guiCommand(wave):
    """A LaserTaskGui.generateTask-shaped command for *wave*."""
    return {'shutter': {'command': (wave != 0).astype(float)}, 'powerWaveform': wave, 'ignorePowerWaveform': True}


def test_getResult_records_saved_stimulus():
    stim = _stimulus()
    wave = stim.eval(n_pts=NPTS, sample_rate=RATE).data
    cmd = dict(_guiCommand(wave), stimulus=stim)
    result = _run(cmd)

    prot = result._info[-1]['Protocol']
    saved = prot['power']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == stim
    assert prot['shutter'] == {}
    assert cmd['stimulus'] is stim
    np.testing.assert_array_equal(result['Channel': 'power'], wave)


def test_getResult_without_stimulus():
    prot = _run(_guiCommand(np.zeros(NPTS)))._info[-1]['Protocol']
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
