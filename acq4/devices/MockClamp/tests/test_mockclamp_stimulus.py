"""MockClampTask forwards a top-level 'stimulus' (as sent by test pulses) to its DAQGeneric
'command' channel, so results record it under Protocol['command']['stimulus']."""
import json

import numpy as np
import pytest
from neuroanalysis import stimuli

from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, runTask
from acq4.devices.DAQGeneric.tests.test_daqgeneric_subclass_results import FakeMockClamp

RATE = 10e3
NPTS = 1000


@pytest.fixture
def dm():
    dm = FakeManager()
    WaveDAQ(dm)
    FakeMockClamp(dm, 'Clamp1')
    return dm


def _run(dm, clampCmd):
    """Run *clampCmd* for device 'Clamp1' through a real Manager.Task; return its result."""
    command = {'protocol': {'duration': NPTS / RATE}, 'DAQ': {'rate': RATE, 'numPts': NPTS}, 'Clamp1': clampCmd}
    return runTask(dm, command)[1]['Clamp1']


def test_test_pulse_command_records_stimulus(dm):
    square = stimuli.SquarePulse(start_time=5e-3, duration=10e-3, amplitude=-10e-3)
    cmdData = square.eval(n_pts=NPTS, sample_rate=RATE).data - 70e-3
    cmd = {'mode': 'VC', 'command': cmdData, 'stimulus': square}
    prot = _run(dm, cmd)._info[-1]['Protocol']
    saved = prot['command']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == square
    assert 'command' not in prot['command']

    # what TestPulseThread reads back is still the object
    assert cmd['stimulus'] is square
    assert cmd['daqProtocol']['command']['stimulus'] is square
    assert cmd['daqProtocol']['command']['command'] is cmdData


def test_task_gui_command_records_stimulus(dm):
    # MockClampTaskGui sends the stimulus inside daqProtocol, as DAQGeneric channels do
    stim = stimuli.Stimulus(items=[stimuli.Offset(-70e-3)])
    cmd = {'mode': 'VC', 'daqProtocol': {'command': {'command': np.zeros(NPTS), 'stimulus': stim}}}
    prot = _run(dm, cmd)._info[-1]['Protocol']
    assert stimuli.Stimulus.load(prot['command']['stimulus']) == stim


def test_command_without_stimulus(dm):
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS)}
    prot = _run(dm, cmd)._info[-1]['Protocol']
    assert 'stimulus' not in prot['command']
