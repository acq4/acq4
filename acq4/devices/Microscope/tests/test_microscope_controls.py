"""Objective lift/dip control-surface buttons on :class:`~acq4.devices.Microscope.Microscope`.

Everything here runs headless against :class:`MockControlSurface` and :class:`MockStage`; no
hardware is involved. The stand-in device manager borrows the *real* :meth:`Manager.move` and
:meth:`Manager.reserveDevices`, so a button press travels the production path -- through the
motion planner, its Panic Lock check and its device reservation -- rather than a shortcut
invented for the test. Control signals and transform updates both arrive over queued
connections, so tests pump the Qt event loop after injecting activity.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from acq4.Manager import Manager
from acq4.devices.MockControlSurface import MockControlSurface
from acq4.devices.MockStage import MockStage
from acq4.devices.Microscope import Microscope
from acq4.motion.plan import AtomicMove, SequentialGroup
from acq4.motion.planner import MotionPlanner
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util import Qt

UM = 1e-6
MM = 1e-3

LIFT_HEIGHT = 5 * MM
DIP_HEIGHT = -50 * UM

#: Display buttons -- the shape of a Stream Dock key: text, image and any colour.
LIFT_BTN = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ('img', 0, 0)}
DIP_BTN = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ('img', 0, 1)}
#: A lit-but-displayless button -- the shape of an X-Keys key.
LIT_BTN = {'device': 'Dock', 'type': 'button', 'page': 0, 'key': ('lit', 0, 0)}
#: Not a button at all.
DIAL = {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': 'jog'}


def pump(iterations=5):
    """Deliver queued Qt events so that control and transform signals arrive."""
    for _ in range(iterations):
        Qt.QApplication.processEvents()


def drainErrorMonitors(timeout=5.0):
    """Join gentletask's error-monitor threads.

    A refused move is reported by ``asynch(raise_errors=...)`` raising on a daemon monitor
    thread of its own. Left running, that raise lands during whichever test happens to be
    executing when the task finally fails, and pytest attributes the unhandled thread
    exception *there*. Joining it inside the test that provoked it keeps the report -- and
    the ``filterwarnings`` mark that expects it -- where it belongs.
    """
    for thread in threading.enumerate():
        if thread.name.startswith('error-monitor'):
            thread.join(timeout)


def pumpUntil(predicate, timeout=10.0):
    """Pump the event loop until *predicate* is true or *timeout* elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        Qt.QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


class TrivialPlanner(MotionPlanner):
    """Plan each spec as one :class:`AtomicMove`, with no geometry.

    The point is to run the real :meth:`MotionPlanner.execute` -- Panic Lock check, device
    reservation, plan execution -- without dragging a rig's worth of pipette geometry in.
    Borrowed from ``acq4/motion/tests/test_move_reservation.py``.
    """

    def plan(self, specs, name=""):
        steps = [
            AtomicMove(
                device=s.device, position=s.position, speed=s.speed, explanation=name or "move"
            )
            for s in specs
        ]
        return steps[0] if len(steps) == 1 else SequentialGroup(steps=steps)


class MockDM(Qt.QObject):
    """Just enough device manager for a Microscope, a stage and one control surface.

    ``move`` and ``reserveDevices`` are the real Manager methods, bound to this stand-in, so
    that the lift/dip path is exercised end to end. Config files live in a dict rather than on
    disk, which is also how a test seeds or reads back an objective's stored heights.
    """

    sigConfigChanged = Qt.Signal()

    #: Short, so that a mistakenly cross-thread reservation fails fast instead of hanging.
    RESERVE_TIMEOUT = 2.0

    def __init__(self):
        Qt.QObject.__init__(self)
        self.globalHalt = GlobalHalt()
        self.devices = {}
        self.configFiles = {}
        self.moveSpecs = []  # every MoveSpec handed to move(), in order
        self.moveTasks = []  # the task each move() call returned
        self._planner = TrivialPlanner()

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def listDevices(self):
        return list(self.devices)

    def configFileName(self, filename):
        return filename

    def readConfigFile(self, filename):
        return dict(self.configFiles.get(filename, {}))

    def writeConfigFile(self, data, filename):
        self.configFiles[filename] = dict(data)
        return data

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return Manager.reserveDevices(
            self, devices, timeout=self.RESERVE_TIMEOUT, reserver=reserver
        )

    @property
    def motionPlanner(self):
        return self._planner

    def move(self, *specs, name: str = ""):
        self.moveSpecs.extend(specs)
        task = Manager.move(self, *specs, name=name)
        self.moveTasks.append(task)
        return task


def scopeConfig(controls=None, presets=None, slots=('0',)):
    config = {
        'driver': 'Microscope',
        'parentDevice': 'Stage',
        'objectives': {slot: {f'{slot}obj': {'name': f'objective {slot}'}} for slot in slots},
    }
    if controls:
        config['controls'] = controls
    if presets:
        config['presets'] = presets
    return config


class Rig:
    """A mock surface and stage, plus a factory for microscopes bound to them."""

    def __init__(self, monkeypatch, surfaceClass=MockControlSurface):
        self.dm = MockDM()
        # acquireControlFromConfig and the motion planner both resolve the global manager.
        monkeypatch.setattr('acq4.Manager.Manager.single', self.dm, raising=False)
        self.surface = surfaceClass(self.dm, {}, 'Dock')
        self.dm.devices['Dock'] = self.surface
        # Both speeds are brisk: these tests care about millimetres and about which speed
        # reached the move, not about how long a real stage would take to travel.
        self.stage = MockStage(
            self.dm,
            {'driver': 'MockStage', 'nAxes': 3, 'fastSpeed': 100 * MM, 'slowSpeed': 20 * MM},
            'Stage',
        )
        self.dm.devices['Stage'] = self.stage
        self.scopes = []

    def makeScope(self, controls=None, presets=None, slots=('0',)):
        scope = Microscope(
            self.dm, scopeConfig(controls, presets, slots), f'Scope{len(self.scopes)}'
        )
        self.scopes.append(scope)
        self.dm.devices[scope.name()] = scope
        pump()
        return scope

    def control(self, spec):
        return self.surface.getControl(spec['type'], spec['page'], spec['key'])

    def press(self, spec):
        """Press a button and return the task of the move it started.

        The press is delivered on the GUI thread, the mover runs on a worker thread and the
        plan on another again, so this waits -- pumping, so that position and transform
        signals keep arriving -- for the move task to appear and then to finish.
        """
        before = len(self.dm.moveTasks)
        self.surface.mockPress(spec['type'], spec['key'])
        if not pumpUntil(lambda: len(self.dm.moveTasks) > before, timeout=5.0):
            return None
        task = self.dm.moveTasks[-1]
        pumpUntil(lambda: task.is_done)
        self.settle()
        return task

    def settle(self):
        """Wait for the stage to stop and for its position to reach the microscope."""
        pumpUntil(lambda: not self.stage.isMoving())
        pump(10)

    def quit(self):
        for scope in self.scopes:
            scope.quit()
        self.stage.quit()


@pytest.fixture
def rig(qapp, monkeypatch):
    r = Rig(monkeypatch)
    yield r
    r.quit()


def setHeights(scope, lift=LIFT_HEIGHT, dip=DIP_HEIGHT):
    """Store lift/dip heights on the currently selected objective, as the rack GUI does."""
    obj = scope.getObjective()
    if lift is not None:
        obj.setLiftHeight(lift)
    if dip is not None:
        obj.setDipHeight(dip)
    pump()


def textWrites(rig, spec):
    return [w for w in rig.surface.writesFor(rig.control(spec)) if w['op'] == 'text']


# --------------------------------------------------------------------------- binding


class TestBinding:
    def test_no_controls_block_is_a_noop(self, rig):
        scope = rig.makeScope()
        assert scope._boundControls == {}
        assert scope._liftDipControls == {}
        assert rig.control(LIFT_BTN).owner is None
        assert rig.surface.writes == []

        rig.surface.mockPress(LIFT_BTN['type'], LIFT_BTN['key'])
        pump(10)
        assert rig.dm.moveSpecs == []

    def test_binding_acquires_the_controls(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        assert set(scope._boundControls) == {'lift', 'dip'}
        assert rig.control(LIFT_BTN).owner is scope
        assert rig.control(DIP_BTN).owner is scope

    def test_control_names_are_lift_and_dip(self, rig):
        scope = rig.makeScope()
        assert sorted(scope.controlNames()) == ['dip', 'lift']

    def test_quit_releases_the_controls(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        scope.quit()
        assert scope._boundControls == {}
        assert scope._liftDipControls == {}
        assert rig.control(LIFT_BTN).owner is None
        assert rig.control(DIP_BTN).owner is None

    def test_quit_releases_preset_controls_too(self, rig):
        scope = rig.makeScope(presets={'gfp': {'control': dict(LIT_BTN)}})
        assert rig.control(LIT_BTN).owner is scope
        scope.quit()
        assert rig.control(LIT_BTN).owner is None

    def test_unknown_control_name_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="unknown control name"):
            rig.makeScope({'park': LIFT_BTN})

    def test_a_failed_binding_leaves_nothing_claimed(self, rig):
        # Acquisition is strictly once until released and a device whose construction
        # raises is never quit(), so a half-finished 'controls:' block must not leak.
        with pytest.raises(ValueError):
            rig.makeScope({'lift': LIFT_BTN, 'park': DIP_BTN})
        assert rig.control(LIFT_BTN).owner is None
        assert rig.control(DIP_BTN).owner is None

    def test_a_dial_is_a_config_error(self, rig):
        with pytest.raises(ValueError, match="not a button"):
            rig.makeScope({'lift': DIAL})


# --------------------------------------------------------------------------- movement


class TestMovement:
    def test_lift_moves_focus_to_the_objectives_lift_height(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        setHeights(scope)
        rig.press(LIFT_BTN)

        assert [s.device for s in rig.dm.moveSpecs] == [rig.stage]
        np.testing.assert_allclose(rig.dm.moveSpecs[-1].position, [0, 0, LIFT_HEIGHT], atol=1e-9)
        np.testing.assert_allclose(scope.getFocusDepth(), LIFT_HEIGHT, atol=UM)

    def test_dip_returns_to_the_dip_height(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        setHeights(scope)
        rig.press(LIFT_BTN)
        rig.press(DIP_BTN)
        np.testing.assert_allclose(scope.getFocusDepth(), DIP_HEIGHT, atol=UM)

    def test_dip_is_absolute_even_after_the_stage_moved_while_raised(self, rig):
        # The whole reason both destinations are read from the objective rather than
        # captured when lifting: driving the scope around while it is up must not move
        # where "down" is.
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        setHeights(scope)
        rig.press(LIFT_BTN)
        rig.stage.move([2 * MM, 3 * MM, LIFT_HEIGHT + 2 * MM], speed='fast').wait(timeout=10)
        rig.settle()

        rig.press(DIP_BTN)
        np.testing.assert_allclose(scope.getFocusDepth(), DIP_HEIGHT, atol=UM)

    def test_lift_is_idempotent(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN})
        setHeights(scope)
        rig.press(LIFT_BTN)
        rig.press(LIFT_BTN)
        np.testing.assert_allclose(scope.getFocusDepth(), LIFT_HEIGHT, atol=UM)

    def test_speed_option_reaches_the_move(self, rig):
        scope = rig.makeScope({'lift': dict(LIFT_BTN, speed='slow')})
        setHeights(scope)
        rig.press(LIFT_BTN)
        assert rig.dm.moveSpecs[-1].speed == 'slow'

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_the_move_goes_through_the_panic_lock(self, rig):
        # setFocusDepth -> Manager.move -> MotionPlanner.execute, whose first act is
        # globalHalt.check(). Nothing in Microscope re-checks it or goes round it, so a
        # halted rig refuses the button with no extra machinery here. (The refusal is
        # reported on an error-monitor thread, as any failed detached move is; hence the
        # warning filter.)
        scope = rig.makeScope({'lift': LIFT_BTN})
        setHeights(scope)
        rig.dm.globalHalt.halt("test")
        try:
            task = rig.press(LIFT_BTN)
            with pytest.raises(GlobalHaltException):
                task.wait(timeout=5)
            np.testing.assert_allclose(rig.stage.getPosition(), [0, 0, 0], atol=1e-9)
            np.testing.assert_allclose(scope.getFocusDepth(), 0, atol=1e-9)
            drainErrorMonitors()
        finally:
            rig.dm.globalHalt.resume()


class TestMissingHeight:
    """A height that was never captured has nowhere to go, and says so."""

    def test_lift_without_a_height_raises(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        with pytest.raises(RuntimeError, match="No lift height set"):
            scope.moveLift()

    def test_dip_without_a_height_raises(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        with pytest.raises(RuntimeError, match="No dip height set"):
            scope.moveDip()

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_pressing_the_button_moves_nothing(self, rig):
        # The refusal is surfaced the way a failed preset is, on an error-monitor thread
        # (asynch(raise_errors=...)); what matters here is that no motion was attempted.
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        rig.surface.mockPress(LIFT_BTN['type'], LIFT_BTN['key'])
        pump(20)
        assert rig.dm.moveSpecs == []
        np.testing.assert_allclose(scope.getFocusDepth(), 0, atol=1e-9)
        drainErrorMonitors()

    def test_the_button_says_so(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        pumpUntil(lambda: textWrites(rig, LIFT_BTN), timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['text'] == 'Lift\n(unset)'
        assert textWrites(rig, DIP_BTN)[-1]['text'] == 'Dip\n(unset)'

        setHeights(scope)
        assert textWrites(rig, LIFT_BTN)[-1]['text'] == 'Lift'
        assert textWrites(rig, DIP_BTN)[-1]['text'] == 'Dip'


# ---------------------------------------------------------------------------- output


class TestOutput:
    def test_label_option_overrides_the_default(self, rig):
        scope = rig.makeScope({'lift': dict(LIFT_BTN, label='Up')})
        setHeights(scope)
        pumpUntil(lambda: textWrites(rig, LIFT_BTN), timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['text'] == 'Up'

    def test_a_display_button_is_highlighted_while_focus_is_at_its_height(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN, 'dip': DIP_BTN})
        setHeights(scope)
        pumpUntil(lambda: textWrites(rig, LIFT_BTN), timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['background'] is None

        rig.press(LIFT_BTN)
        pumpUntil(lambda: textWrites(rig, LIFT_BTN)[-1]['background'] is not None, timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['background'] == scope.liftDipActiveBackground
        assert textWrites(rig, DIP_BTN)[-1]['background'] is None

        rig.press(DIP_BTN)
        pumpUntil(lambda: textWrites(rig, DIP_BTN)[-1]['background'] is not None, timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['background'] is None
        assert textWrites(rig, DIP_BTN)[-1]['background'] == scope.liftDipActiveBackground

    def test_an_unchanged_state_is_not_repainted(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN})
        setHeights(scope)
        pumpUntil(lambda: textWrites(rig, LIFT_BTN), timeout=2.0)
        rig.surface.clearWrites()
        # a focus move that neither enters nor leaves the lift height's tolerance band
        rig.stage.move([0, 0, 1 * MM], speed='fast').wait(timeout=10)
        rig.settle()
        assert rig.surface.writes == []

    def test_an_led_only_button_lights_while_focus_is_at_its_height(self, rig):
        scope = rig.makeScope({'lift': LIT_BTN})
        setHeights(scope)
        pump()
        colors = [w['color'].name() for w in rig.surface.writesFor(rig.control(LIT_BTN))]
        assert colors and colors[-1] == '#000000'  # unlit to start

        rig.press(LIT_BTN)
        pumpUntil(
            lambda: rig.surface.writesFor(rig.control(LIT_BTN))[-1]['color'].green() == 0
            and rig.surface.writesFor(rig.control(LIT_BTN))[-1]['color'].name() != '#000000',
            timeout=2.0,
        )
        assert rig.surface.writesFor(rig.control(LIT_BTN))[-1]['color'].name() == '#ff00ff'

    def test_a_button_with_no_output_still_moves_and_says_so_once(self, qapp, monkeypatch, caplog):
        class BlindSurface(MockControlSurface):
            """A mock whose display buttons have no output at all."""

            IMAGE_BUTTON_CAPS = {'input': {'press': True}, 'output': {}}

        rig = Rig(monkeypatch, BlindSurface)
        try:
            with caplog.at_level('WARNING'):
                scope = rig.makeScope({'lift': LIFT_BTN})
            assert sum('will not show anything' in r.message for r in caplog.records) == 1
            assert rig.surface.writes == []

            setHeights(scope)
            rig.press(LIFT_BTN)
            np.testing.assert_allclose(scope.getFocusDepth(), LIFT_HEIGHT, atol=UM)
        finally:
            rig.quit()

    def test_swapping_objectives_repaints(self, rig):
        scope = rig.makeScope({'lift': LIFT_BTN}, slots=('0', '1'))
        setHeights(scope)
        pumpUntil(lambda: textWrites(rig, LIFT_BTN), timeout=2.0)
        assert textWrites(rig, LIFT_BTN)[-1]['text'] == 'Lift'

        scope.setObjectiveIndex('1')
        pump(10)
        assert textWrites(rig, LIFT_BTN)[-1]['text'] == 'Lift\n(unset)'
