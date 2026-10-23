"""Tests of Microscope.loadPreset and initialPreset: what they resolve before driving anything.

The device manager, objective switch and preset devices are fakes; the Microscope is real.
"""

from __future__ import annotations


import pytest

from acq4.devices.Microscope import Microscope
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util import Qt


def pump(iterations=5):
    for _ in range(iterations):
        Qt.QApplication.processEvents()


@pytest.fixture(scope='module')
def qapplication():
    return Qt.QApplication.instance() or Qt.QApplication([])


class FakeSwitch(Qt.QObject):
    """An objective switch that records every position it is driven to."""

    sigSwitchChanged = Qt.Signal(object, object)

    def __init__(self):
        Qt.QObject.__init__(self)
        self.position = 0
        self.setSwitchCalls = []

    def getSwitch(self, switchId):
        return self.position

    def setSwitch(self, switchId, value):
        self.setSwitchCalls.append((switchId, value))
        self.position = value


class FakePresetDevice:
    """A device a preset can name; records the states it is handed."""

    def __init__(self):
        self.states = []

    def loadPreset(self, state):
        self.states.append(state)


class FakeDM(Qt.QObject):
    """Just enough device manager for a Microscope with presets."""

    sigConfigChanged = Qt.Signal()

    def __init__(self):
        Qt.QObject.__init__(self)
        self.globalHalt = GlobalHalt()
        self.devices = {}

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def configFileName(self, filename):
        return filename

    def readConfigFile(self, filename):
        return {}


@pytest.fixture
def dm(qapplication, monkeypatch):
    manager = FakeDM()
    monkeypatch.setattr('acq4.Manager.Manager.single', manager, raising=False)
    return manager


def makeScope(dm, presets, initialPreset=None, name='Scope'):
    dm.devices['Switch'] = FakeSwitch()
    config = {
        'driver': 'Microscope',
        'objectiveSwitch': ['Switch', 'objSwitch'],
        'objectives': {
            slot: {f'{slot}obj': {'name': f'objective {slot}'}} for slot in ('0', '1')
        },
        'presets': presets,
    }
    if initialPreset is not None:
        config['initialPreset'] = initialPreset
    scope = Microscope(dm, config, name)
    dm.devices[name] = scope
    return scope


class TestLoadingAPreset:
    def test_an_armed_rig_loads_the_preset(self, dm):
        lamp = FakePresetDevice()
        dm.devices['LEDs'] = lamp
        scope = makeScope(dm, {'GFP': {'objective': 1, 'LEDs': {'channel': 'Blue'}}})

        scope.loadPreset('GFP')

        assert dm.devices['Switch'].setSwitchCalls == [('objSwitch', 1)]
        assert lamp.states == [{'channel': 'Blue'}]


class TestAPresetNamingAMissingDevice:
    """A preset naming an unknown device raises KeyError before anything moves, including
    the turret."""

    def test_the_turret_does_not_move_first(self, dm):
        scope = makeScope(dm, {'GFP': {'objective': 1, 'LEDz': {'channel': 'Blue'}}})
        switch = dm.devices['Switch']

        with pytest.raises(KeyError):
            scope.loadPreset('GFP')

        assert switch.setSwitchCalls == [], \
            "the turret turned before the preset's bad device name was found"

    def test_no_device_in_the_preset_is_driven(self, dm):
        lamp = FakePresetDevice()
        dm.devices['LEDs'] = lamp
        scope = makeScope(dm, {'GFP': {'LEDs': {'channel': 'Blue'}, 'LEDz': {}}})

        with pytest.raises(KeyError):
            scope.loadPreset('GFP')

        assert lamp.states == [], "a device was driven for a preset that cannot be applied"

    def test_the_scope_is_left_in_no_named_preset(self, dm):
        scope = makeScope(dm, {'GFP': {'LEDz': {}}})

        with pytest.raises(KeyError):
            scope.loadPreset('GFP')

        assert scope._activePreset is None


class TestTheInitialPreset:
    def test_a_preset_name_that_is_not_configured_is_refused_at_construction(self, dm):
        with pytest.raises(ValueError, match='initialPreset'):
            makeScope(dm, {'GFP': {'objective': 1}}, initialPreset='GFPP')

    def test_it_is_applied_when_the_config_is_finished(self, dm):
        lamp = FakePresetDevice()
        dm.devices['LEDs'] = lamp
        scope = makeScope(dm, {'GFP': {'LEDs': {'channel': 'Blue'}}}, initialPreset='GFP')

        dm.sigConfigChanged.emit()
        pump()

        assert lamp.states == [{'channel': 'Blue'}]


