"""AxoPatch200Task forwards a top-level 'stimulus' to its DAQGeneric 'command' channel."""
from types import SimpleNamespace

import numpy as np
from neuroanalysis import stimuli

from acq4.devices.AxoPatch200.AxoPatch200 import AxoPatch200Task


def test_stimulus_forwarded_to_command_channel():
    square = stimuli.SquarePulse(start_time=5e-3, duration=10e-3, amplitude=-10e-3)
    cmd = {'mode': 'VC', 'command': np.zeros(100), 'stimulus': square}
    AxoPatch200Task(SimpleNamespace(hasSecondaryChannel=False), cmd, None)
    assert cmd['daqProtocol']['command']['stimulus'] is square
    assert cmd['stimulus'] is square


def test_no_stimulus():
    cmd = {'mode': 'VC', 'command': np.zeros(100)}
    AxoPatch200Task(SimpleNamespace(hasSecondaryChannel=False), cmd, None)
    assert 'stimulus' not in cmd['daqProtocol']['command']
