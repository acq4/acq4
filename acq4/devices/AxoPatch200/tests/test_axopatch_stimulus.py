"""AxoPatch200Task forwards a top-level 'stimulus' to its DAQGeneric 'command' channel, so results
record it under Protocol['command']['stimulus']."""
import json

import numpy as np
import pytest
from neuroanalysis import stimuli

from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, runTask

RATE = 10e3
NPTS = 1000


@pytest.fixture
def dm(qtbot):
    from acq4.devices.AxoPatch200.AxoPatch200 import AxoPatch200

    dm = FakeManager()
    WaveDAQ(dm)
    tel = {'device': 'DAQ', 'type': 'ai'}
    axo = AxoPatch200(dm, {
        'version': '200B',
        'ModeChannel': dict(tel, channel='/Dev1/ai13'),
        'GainChannel': dict(tel, channel='/Dev1/ai14'),
        'LPFChannel': dict(tel, channel='/Dev1/ai15'),
        'Command': {'device': 'DAQ', 'channel': '/Dev1/ao0', 'type': 'ao'},
        'ScaledSignal': {'device': 'DAQ', 'channel': '/Dev1/ai5', 'type': 'ai'},
    }, 'Axo')
    yield dm
    axo.modeDialog.close()


def _run(dm, axoCmd):
    """Run *axoCmd* for device 'Axo' through a real Manager.Task; return its result."""
    command = {'protocol': {'duration': NPTS / RATE}, 'DAQ': {'rate': RATE, 'numPts': NPTS}, 'Axo': axoCmd}
    return runTask(dm, command)[1]['Axo']


def test_stimulus_forwarded_to_command_channel(dm):
    # no 'mode': AxoPatch200.setMode asks the user to switch the amplifier
    square = stimuli.SquarePulse(start_time=5e-3, duration=10e-3, amplitude=-10e-3)
    cmd = {'command': square.eval(n_pts=NPTS, sample_rate=RATE).data, 'stimulus': square}
    result = _run(dm, cmd)
    assert cmd['daqProtocol']['command']['stimulus'] is square
    assert cmd['stimulus'] is square

    saved = result._info[-1]['Protocol']['command']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == square


def test_no_stimulus(dm):
    cmd = {'command': np.zeros(NPTS)}
    result = _run(dm, cmd)
    assert 'stimulus' not in cmd['daqProtocol']['command']
    assert 'stimulus' not in result._info[-1]['Protocol']['command']
