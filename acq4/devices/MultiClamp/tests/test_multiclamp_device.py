"""MultiClamp device-level helpers that need no MCC: signal selection, command sensitivity, I=0 switch."""

from contextlib import nullcontext

import pytest

from acq4.devices.MultiClamp.multiclamp import MultiClamp


class _Channel:
    def __init__(self, mode='IC'):
        self.mode = mode
        self.calls = []

    def getMode(self):
        return self.mode

    def setMode(self, mode):
        self.calls.append(('setMode', mode))
        self.mode = mode

    def setPrimarySignal(self, signal):
        self.calls.append(('primary', signal))

    def setSecondarySignal(self, signal):
        self.calls.append(('secondary', signal))


class _Dm:
    def reserveDevices(self, devices, reserver=None):
        return nullcontext()


def bareClamp(mode='IC'):
    dev = MultiClamp.__new__(MultiClamp)
    dev.mc = _Channel(mode)
    dev.dm = _Dm()
    dev._paramCache = {'PrimarySignal': 'x', 'SecondarySignal': 'y'}
    dev.lastState = {}
    dev._switchingToMode = None
    dev.stateLock = nullcontext()
    dev.name = lambda: 'Clamp1'
    return dev


def test_set_signals_go_to_the_driver_and_clear_the_cache():
    dev = bareClamp()
    dev.setPrimarySignal('Membrane Potential')
    dev.setSecondarySignal('Membrane Current')
    assert dev.mc.calls == [('primary', 'Membrane Potential'), ('secondary', 'Membrane Current')]
    assert dev._paramCache == {}


def test_ext_cmd_scale_fallback_matches_telegraph_units():
    dev = bareClamp()
    dev.getLastState = lambda mode=None: None
    assert dev.extCmdScale('VC') == pytest.approx(20e-3)  # V/V, as dExtCmdSens
    assert dev.extCmdScale('IC') == pytest.approx(400e-12)  # A/V


def test_switch_to_zero_current_requires_ic():
    dev = bareClamp('IC')
    assert isinstance(dev.switchToZeroCurrent(), float)
    assert dev.mc.calls == [('setMode', 'I=0')] and dev._switchingToMode == 'I=0'
    with pytest.raises(ValueError, match='requires IC'):
        bareClamp('VC').switchToZeroCurrent()
