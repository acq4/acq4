"""Loading a microscope preset, and the startup preset that loads itself.

``loadPreset`` physically rotates the objective turret. ``initialPreset`` does it
unattended, from ``sigConfigChanged`` at the end of ``Manager.configure()`` --
before any window exists and with nobody watching. These cover what it checks
before it moves anything, and that a preset naming a device that is not there
fails before the nosepiece turns rather than after.

Headless: the device manager, the objective switch and the preset's own devices
are stand-ins, but the Microscope and its preset machinery are the real ones.
"""

from __future__ import annotations

import logging

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


class TestAHaltedRigDoesNotMoveTheTurret:
    """``loadPreset`` drives the nosepiece; the Panic Lock has to reach it.

    The startup preset is the case that matters: it fires from sigConfigChanged,
    before showGUI() has created the Esc shortcut, so a halt latched from the
    focus-independent key is the only thing that can stop it.
    """

    def test_loading_a_preset_while_halted_raises(self, dm):
        scope = makeScope(dm, {'GFP': {'objective': 1}})
        dm.globalHalt.halt("test")

        with pytest.raises(GlobalHaltException):
            scope.loadPreset('GFP')

    def test_the_turret_does_not_move_while_halted(self, dm):
        scope = makeScope(dm, {'GFP': {'objective': 1}})
        switch = dm.devices['Switch']
        dm.globalHalt.halt("test")

        with pytest.raises(GlobalHaltException):
            scope.loadPreset('GFP')

        assert switch.setSwitchCalls == [], "the objective turret turned while halted"

    def test_the_preset_devices_are_not_driven_while_halted(self, dm):
        lamp = FakePresetDevice()
        dm.devices['LEDs'] = lamp
        scope = makeScope(dm, {'GFP': {'LEDs': {'channel': 'Blue'}}})
        dm.globalHalt.halt("test")

        with pytest.raises(GlobalHaltException):
            scope.loadPreset('GFP')

        assert lamp.states == []

    def test_an_armed_rig_loads_the_preset(self, dm):
        lamp = FakePresetDevice()
        dm.devices['LEDs'] = lamp
        scope = makeScope(dm, {'GFP': {'objective': 1, 'LEDs': {'channel': 'Blue'}}})

        scope.loadPreset('GFP')

        assert dm.devices['Switch'].setSwitchCalls == [('objSwitch', 1)]
        assert lamp.states == [{'channel': 'Blue'}]


class TestAPresetNamingAMissingDevice:
    """Only the preset's *name* was checked at config time.

    A typo'd device name inside it reached getDevice() mid-apply, raising KeyError
    on a worker thread into a log line -- by which time setObjectiveIndex may
    already have driven the turret.
    """

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

    def test_it_does_not_move_the_turret_on_a_halted_rig(self, dm):
        scope = makeScope(dm, {'GFP': {'objective': 1}}, initialPreset='GFP')
        switch = dm.devices['Switch']
        dm.globalHalt.halt("panic key pressed during startup")

        dm.sigConfigChanged.emit()
        pump()

        assert switch.setSwitchCalls == [], \
            "the startup preset turned the turret on a halted rig"

    def test_a_halt_is_reported_rather_than_escalated(self, dm, caplog):
        """Unattended, on a detached task: a halt is a refusal, not a failure.

        Raised instead, it reaches an error monitor thread and is reported as an
        error loading the preset, which says nothing about why.
        """
        caplog.set_level(logging.INFO)
        scope = makeScope(dm, {'GFP': {'objective': 1}}, initialPreset='GFP')
        dm.globalHalt.halt("panic key pressed during startup")

        scope._loadPresetUnlessHalted('GFP')

        assert any('halted' in record.message for record in caplog.records), \
            "nothing said why the startup preset was skipped"
