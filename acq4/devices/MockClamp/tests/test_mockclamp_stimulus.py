"""MockClampTask forwards a top-level 'stimulus' (as sent by test pulses) to its DAQGeneric
'command' channel, so results record it under Protocol['command']['stimulus']."""
import json

import numpy as np
from neuroanalysis import stimuli

from acq4.devices.MockClamp.MockClamp import MockClampTask

RATE = 10e3
NPTS = 1000


class _FakeDaqTask:
    def getData(self, channel):
        return {'data': np.zeros(NPTS), 'info': {'rate': RATE, 'numPts': NPTS, 'startTime': 1000.0}}


class _IdentityMapping:
    def mapFromDaq(self, ch, data):
        return data


class _FakeDaqDev:
    _DGConfig = {
        'command': {'type': 'ao', 'channel': ('DAQ', '/Dev1/ao0'), 'units': 'V'},
        'primary': {'type': 'ai', 'channel': ('DAQ', '/Dev1/ai0'), 'units': 'A'},
    }

    def getChanUnits(self, ch):
        return self._DGConfig[ch]['units']


class _FakeMockClamp:
    daqDev = _FakeDaqDev()

    def getHolding(self, mode):
        return -70e-3


def _executedTask(cmd):
    task = MockClampTask(_FakeMockClamp(), cmd, None)
    task.bufferedChannels = ['command', 'primary']
    task.daqTasks = {ch: _FakeDaqTask() for ch in task.bufferedChannels}
    task.mapping = _IdentityMapping()
    task.holdingVals = {'command': -70e-3}
    task.ampState = {'mode': cmd['mode']}
    return task


def test_test_pulse_command_records_stimulus():
    square = stimuli.SquarePulse(start_time=5e-3, duration=10e-3, amplitude=-10e-3)
    cmdData = square.eval(n_pts=NPTS, sample_rate=RATE).data - 70e-3
    cmd = {'mode': 'VC', 'command': cmdData, 'stimulus': square}
    task = _executedTask(cmd)
    assert cmd['daqProtocol']['command']['stimulus'] is square

    prot = task.getResult()._info[-1]['Protocol']
    saved = prot['command']['stimulus']
    assert isinstance(saved, dict)
    json.dumps(saved)
    assert stimuli.Stimulus.load(saved) == square
    assert 'command' not in prot['command']

    # what TestPulseThread reads back is still the object
    assert cmd['stimulus'] is square
    assert cmd['daqProtocol']['command']['stimulus'] is square
    assert cmd['daqProtocol']['command']['command'] is cmdData


def test_task_gui_command_records_stimulus():
    # MockClampTaskGui sends the stimulus inside daqProtocol, as DAQGeneric channels do
    stim = stimuli.Stimulus(items=[stimuli.Offset(-70e-3)])
    cmd = {'mode': 'VC', 'daqProtocol': {'command': {'command': np.zeros(NPTS), 'stimulus': stim}}}
    prot = _executedTask(cmd).getResult()._info[-1]['Protocol']
    assert stimuli.Stimulus.load(prot['command']['stimulus']) == stim


def test_command_without_stimulus():
    cmd = {'mode': 'VC', 'command': np.zeros(NPTS)}
    prot = _executedTask(cmd).getResult()._info[-1]['Protocol']
    assert 'stimulus' not in prot['command']
