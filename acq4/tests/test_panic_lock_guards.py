"""Panic Lock guards — the §13 "Guards" section of ``Panic Lock Spec.md``.

Sibling to ``test_panic_lock.py``, which covers ``GlobalHalt`` in isolation with
mock callables. This file needs the opposite: real device classes, real guards,
and one shared ``GlobalHalt`` that every participant registers against, so the
§6.1 table and the §6.3 contract are checked against the code that actually runs.

No hardware. The devices here are ACQ4's own mock/base classes wired to a
stand-in Manager (``_RigManager``) that borrows the real ``Manager`` methods for
everything the guards touch: ``runTask``, ``abortAllTasks``, the task registry
and ``reserveDevices``. Where a class cannot be built without a GUI (the
``Imager`` module), the real function is bound to a minimal object so the code
under test is still the shipped code.

The centrepiece is ``TestHaltPathContract``: it halts the rig and then requires
every callback in the registry -- not a list written down here -- to complete.
A guard added later that blocks a halt-path action fails that test by name.
"""

from __future__ import annotations

import threading
import time
import weakref
from unittest import mock

import numpy as np
import pytest

from acq4.Manager import Manager, Task
from acq4.devices.Device import Device, DeviceTask
from acq4.devices.Laser.Laser import Laser
from acq4.devices.MockFilterWheel import MockFilterWheel
from acq4.devices.MockPressureControl import MockPressureControl
from acq4.devices.MockStage import MockStage
from acq4.devices.PatchClamp.patchclamp import PatchClamp
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager
from acq4.devices.PressureControl import PressureControl
from acq4.devices.Scanner.Scanner import Scanner, ScannerTask
from acq4.modules.Imager.Imager import Imager
from acq4.motion.planner import MotionPlanner
from acq4.motion.plan import AtomicMove
from acq4.motion.spec import MoveSpec
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.tests.test_panic_lock import captured_thread_exceptions
from acq4.util import Qt

# Only ever gates a pass, never manufactures one.
TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Stand-ins
# ---------------------------------------------------------------------------


class _FakeDaq:
    """A DAQ that records channel writes instead of making them.

    Standing in for the hardware behind the Scanner's mirror channels, this is
    what "assert the driver was never touched" is asserted against.
    """

    def __init__(self):
        self.writes = []

    def setChannelValue(self, chan, value, block=True):
        self.writes.append((chan, value))

    def verifyChannelBelongs(self, chan):
        pass


class _RecordingPressure(MockPressureControl):
    """MockPressureControl that remembers every write that reached "hardware"."""

    def __init__(self, manager, config, name):
        self.setPressureCalls = []
        self.setSourceCalls = []
        super().__init__(manager, config, name)

    def _setPressure(self, p):
        self.setPressureCalls.append(p)
        super()._setPressure(p)

    def _setSource(self, source):
        self.setSourceCalls.append(source)
        super()._setSource(source)


class _RecordingDeviceTask(DeviceTask):
    """A DeviceTask that records its lifecycle instead of running hardware."""

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.configured = False
        self.started = False
        self.stops = []

    def configure(self):
        self.configured = True

    def start(self):
        self.started = True

    def isDone(self):
        return True

    def stop(self, abort=False):
        self.stops.append(abort)

    def getResult(self):
        return None


class _RecordingDevice(Device):
    """A real Device (real reservation machinery) that hands out recording tasks."""

    def __init__(self, dm, name):
        Device.__init__(self, dm, {}, name)
        self.tasks = []

    def createTask(self, cmd, parentTask):
        task = _RecordingDeviceTask(self, cmd, parentTask)
        self.tasks.append(task)
        return task


class _RigManager:
    """Stands in for the Manager, borrowing the real methods the guards involve.

    ``runTask``, ``abortAllTasks``, the task registry and ``reserveDevices`` are
    the genuine ``Manager`` implementations bound to this object, so the guard in
    ``runTask`` and the halt path through ``abortAllTasks`` are the shipped code.
    """

    def __init__(self):
        self.globalHalt = GlobalHalt()
        self._tasksInProgress = weakref.WeakSet()
        self._taskRegistryLock = threading.Lock()
        self.devices = {}
        self.config = {}
        self.reserveCalls = []
        self.globalHalt.add_abort_callback(self.abortAllTasks, name="Manager")

    # -- device manager surface used by Device.__init__ and friends ----------
    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return self.devices[name]

    def listInterfaces(self, typ):
        return []

    def readConfigFile(self, filename):
        return {}

    def writeConfigFile(self, data, filename):
        return None

    def appendConfigFile(self, data, filename):
        return None

    def configFileName(self, filename):
        return filename

    # -- the real Manager methods under test --------------------------------
    runTask = Manager.runTask
    abortAllTasks = Manager.abortAllTasks
    _taskStarted = Manager._taskStarted
    _taskFinished = Manager._taskFinished

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        self.reserveCalls.append((list(devices), reserver))
        return Manager.reserveDevices(self, devices, timeout=1.0, reserver=reserver)


class _FakeImagingThread:
    """The Imager's acquisition thread: abort() only sets a flag (Imager.py)."""

    def __init__(self):
        self.aborted = False

    def abort(self):
        self.aborted = True


class _ImagerStandIn:
    """The real ``Imager.abortTask``, bound to the two attributes it touches.

    The Imager is a GUI module and cannot be built headless, but its abort
    callback is four lines that reach only ``laserDev`` and ``imagingThread``.
    Binding the real function here runs the shipped halt path -- including the
    ``closeShutter()`` call that has to survive the Laser guard -- without the UI.
    """

    abortTask = Imager.abortTask

    def __init__(self, laserDev):
        self.laserDev = laserDev
        self.imagingThread = _FakeImagingThread()


# -- PatchPipette state-manager stand-ins ------------------------------------


class _FakeStateJob(Qt.QObject):
    """A state job with the surface ``PatchPipetteStateManager`` drives.

    Real ``PatchPipetteState`` subclasses need a full PatchPipette (clamp,
    pressure, pipette, test-pulse feed) to construct. The manager's own
    transition logic -- which is what the guard lives in -- only touches the
    handful of members below, so faking the job keeps the *manager* real.
    """

    sigStateChanged = Qt.Signal(object, object)
    sigFinished = Qt.Signal(object)

    class Timeout(Exception):
        pass

    stateName = None

    #: Every job ever constructed, so a test can assert none was.
    instances = []

    def __init__(self, dev, config):
        Qt.QObject.__init__(self)
        _FakeStateJob.instances.append(self)
        self.dev = dev
        self.config = config
        self.nextState = {"state": None}
        self.started = False
        self.stopped = False
        self.cleanedUp = False
        self._finishCallbacks = []

    @classmethod
    def defaultConfig(cls):
        return {}

    def add_finish_callback(self, cb):
        self._finishCallbacks.append(cb)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def wait(self, timeout=None):
        return None

    def cleanup(self):
        self.cleanedUp = True
        return mock.MagicMock()


class _BathJob(_FakeStateJob):
    stateName = "bath"


class _OutJob(_FakeStateJob):
    stateName = "out"


class _FakeStateManager(PatchPipetteStateManager):
    """The real state manager over fake states (see ``_FakeStateJob``)."""

    stateHandlers = {"bath": _BathJob, "out": _OutJob}


class _FakePipette(Qt.QObject):
    """The slice of PatchPipette that ``PatchPipetteStateManager`` uses."""

    sigStateChanged = Qt.Signal(object, object)
    sigActiveChanged = Qt.Signal(object, object)

    def __init__(self, dm):
        Qt.QObject.__init__(self)
        self.dm = dm
        self.clampDevice = None
        self.pressureDevice = None
        self.stateChanges = []

    def name(self):
        return "FakePipette"

    def _setState(self, state, oldState):
        self.stateChanges.append((oldState, state))


# ---------------------------------------------------------------------------
# The rig
# ---------------------------------------------------------------------------


class _Rig:
    """Every Panic Lock participant, sharing one GlobalHalt."""

    def __init__(self, manager):
        self.manager = manager
        self.globalHalt = manager.globalHalt

    def halt(self, reason="test panic"):
        """Set the latch, with no fan-out: the guard tests are about the latch.

        ``halt()`` always fans out, and the fan-out is *designed* to change device
        state -- it vents the pressure, closes the shutters, stops the stage. Left
        running it would race every "the hardware was never touched" assertion in
        this file and rewrite the very state under test. Unregistering first leaves
        the latch, which is what the guards read. The callbacks get their own,
        stricter, workout in ``TestHaltPathContract``.
        """
        for _, cb in list(self.globalHalt._abortCallbacks):
            self.globalHalt.remove_abort_callback(cb)
        self.globalHalt.halt(reason)


@pytest.fixture
def rig(qtbot, monkeypatch):
    """A complete mock rig: one participant of every class in §5.2."""
    (qtbot,)  # a QApplication must exist for the devices' Qt mutexes and signals

    manager = _RigManager()
    rig = _Rig(manager)

    # Devices reach the Manager through several module-level getManager() calls.
    for target in (
        "acq4.Manager.getManager",
        "acq4.devices.PatchClamp.testpulse.getManager",
        "acq4.devices.PatchPipette.statemanager.getManager",
        "acq4.motion.planner.getManager",
    ):
        monkeypatch.setattr(target, lambda: manager)

    manager.devices["DAQ"] = rig.daq = _FakeDaq()

    with mock.patch("acq4.Manager.Manager.single") as single:
        single.return_value = manager
        rig.stage = MockStage(manager, {"driver": "MockStage", "nAxes": 3}, "Stage")

    rig.pressure = _RecordingPressure(manager, {}, "Pressure")

    rig.laser = Laser(
        manager,
        {
            "shutter": {"type": "do", "channel": "shutterChan"},
            "qSwitch": {"type": "do", "channel": "qSwitchChan"},
            "pCell": {"type": "ao", "channel": "pCellChan"},
        },
        "Laser",
    )

    rig.scanner = Scanner(
        manager,
        {
            "XAxis": {"device": "DAQ", "channel": "/Dev1/ao0", "type": "ao"},
            "YAxis": {"device": "DAQ", "channel": "/Dev1/ao1", "type": "ao"},
            "commandLimits": (-10, 10),
            "offVoltage": (-4.0, -4.0),
        },
        "Scanner",
    )

    rig.filterWheel = MockFilterWheel(
        manager,
        {"slots": {"0": "empty", "1": "GFP"}, "ports": ["input", "output"], "pollInterval": None},
        "FilterWheel",
    )

    class _TestClamp(PatchClamp):
        # The only abstract method reached while building the test pulse thread.
        def getDAQName(self, channel):
            return "DAQ"

    rig.clamp = _TestClamp(manager, {}, "Clamp")

    _FakeStateJob.instances = []
    rig.pipette = _FakePipette(manager)
    # Profiles come from the ACQ4 config file; there is none here.
    monkeypatch.setattr(PatchPipetteStateManager, "_profilesLoadedFromConfig", True)
    rig.stateManager = _FakeStateManager(rig.pipette)

    rig.imager = _ImagerStandIn(rig.laser)
    manager.globalHalt.add_abort_callback(rig.imager.abortTask, name="Imager.abortTask")

    rig.taskDevice = _RecordingDevice(manager, "TaskDev")
    manager.devices["TaskDev"] = rig.taskDevice

    yield rig

    rig.stage.quit()
    rig.clamp.quit()
    rig.filterWheel.quit()


def newTask(rig, devName="TaskDev"):
    """A real Manager.Task over the recording device."""
    return Task(rig.manager, {"protocol": {"duration": 0.0}, devName: {}})


# ---------------------------------------------------------------------------
# §6.1 Stage
# ---------------------------------------------------------------------------


class TestStageGuards:
    def test_move_raises_while_halted_before_touching_the_driver(self, rig):
        stage = rig.stage
        startPos = list(stage.getPosition())
        rig.halt()

        with mock.patch.object(stage, "_move", side_effect=AssertionError("driver touched")) as drv:
            with mock.patch.object(stage, "checkMove", side_effect=AssertionError("checkMove ran")):
                with pytest.raises(GlobalHaltException):
                    stage.move([1e-3, 0, 0], speed="fast")
        assert drv.call_count == 0

        np.testing.assert_allclose(stage.getPosition(), startPos, atol=1e-9)

    def test_move_never_reaches_the_driver_thread(self, rig):
        """The same guard, asserted against MockStage's actual driver.

        ``MockStageThread.setTarget`` is where a MockStage move becomes motion;
        nothing below the guard may call it.
        """
        stage = rig.stage
        rig.halt()
        with mock.patch.object(stage.stageThread, "setTarget") as setTarget:
            with pytest.raises(GlobalHaltException):
                stage.move([1e-3, 0, 0], speed="fast")
        assert setTarget.call_count == 0

    def test_the_move_funnel_covers_every_public_entry_point(self, rig):
        stage = rig.stage
        rig.halt()
        with mock.patch.object(stage, "_move", side_effect=AssertionError("driver touched")):
            with pytest.raises(GlobalHaltException):
                stage.move([1e-3, 0, 0], speed="fast")
            with pytest.raises(GlobalHaltException):
                stage.moveToGlobalNoPlanning([1e-3, 0, 0], speed="fast")
            with pytest.raises(GlobalHaltException):
                stage.step((10e-6, 0, 0), speed="fast")
            with pytest.raises(GlobalHaltException):
                stage.movePath([{"position": [1e-3, 0, 0], "speed": "fast"}]).wait(timeout=TIMEOUT)

    def test_setVelocity_raises_while_halted(self, rig):
        rig.halt()
        with pytest.raises(GlobalHaltException):
            rig.stage.setVelocity([1e-3, 0, 0])

    def test_move_is_allowed_again_after_resume(self, rig):
        rig.halt()
        with pytest.raises(GlobalHaltException):
            rig.stage.move([10e-6, 0, 0], speed="fast")
        rig.globalHalt.resume()
        rig.stage.move([10e-6, 0, 0], speed="fast").wait(timeout=TIMEOUT)

    def test_stop_and_failing_an_in_flight_move_stay_allowed(self, rig):
        stage = rig.stage
        fut = stage.move([5e-3, 0, 0], speed=50e-6)
        assert not fut.is_done
        rig.halt()
        stage.stop()  # Allowed (§6.1) -- must not raise
        with pytest.raises(RuntimeError):
            fut.wait(timeout=TIMEOUT)  # in-flight future failed, also Allowed
        assert fut.is_done


# ---------------------------------------------------------------------------
# §6.1 PressureControl -- the directional rows
# ---------------------------------------------------------------------------


class TestPressureGuards:
    @pytest.mark.parametrize(
        "activeSource,kwargs",
        [
            ("regulator", dict(source="atmosphere")),
            ("regulator", dict(source="atmosphere", pressure=0)),
            ("atmosphere", dict(source="atmosphere", pressure=0)),
            # A bare pressure write is safe only while already vented.
            ("atmosphere", dict(pressure=0)),
            ("atmosphere", dict()),
        ],
    )
    def test_venting_stays_allowed(self, rig, activeSource, kwargs):
        pressure = rig.pressure
        pressure.setPressure(source=activeSource, pressure=0)
        rig.halt()
        pressure.setPressure(**kwargs)  # must not raise
        if "source" in kwargs:
            assert pressure.source == "atmosphere"

    @pytest.mark.parametrize(
        "activeSource,kwargs",
        [
            ("atmosphere", dict(source="regulator", pressure=20e3)),
            ("atmosphere", dict(source="user")),
            ("regulator", dict(source="regulator")),
            # "setPressure(pressure=...) with non-atmosphere source active"
            ("regulator", dict(pressure=20e3)),
            ("user", dict(pressure=-20e3)),
            # Charging the regulator is refused even with atmosphere selected: it
            # stores energy rather than reducing it (§6.1's governing rule).
            ("atmosphere", dict(source="atmosphere", pressure=20e3)),
            ("atmosphere", dict(pressure=20e3)),
        ],
    )
    def test_pressurising_raises_and_never_reaches_hardware(self, rig, activeSource, kwargs):
        pressure = rig.pressure
        pressure.setPressure(source=activeSource, pressure=0)
        rig.halt()
        pressure.setPressureCalls.clear()
        pressure.setSourceCalls.clear()

        with pytest.raises(GlobalHaltException):
            pressure.setPressure(**kwargs)

        assert pressure.setPressureCalls == []
        assert pressure.setSourceCalls == []
        assert pressure.source == activeSource

    def test_setSource_to_a_live_source_raises(self, rig):
        rig.pressure.setPressure(source="atmosphere", pressure=0)
        rig.halt()
        with pytest.raises(GlobalHaltException):
            rig.pressure.setSource("regulator")
        rig.pressure.setSource("atmosphere")  # Allowed

    def test_rampPressure_raises_before_reading_the_device(self, rig):
        pressure = rig.pressure
        pressure.setPressure(source="regulator", pressure=0)
        rig.halt()
        with mock.patch.object(pressure, "getPressure", side_effect=AssertionError("device read")):
            with pytest.raises(GlobalHaltException):
                pressure.rampPressure(target=20e3).wait(timeout=TIMEOUT)
        assert pressure.setPressureCalls == [0]  # only the pre-halt setup write


# ---------------------------------------------------------------------------
# §6.1 Laser
# ---------------------------------------------------------------------------


class TestLaserGuards:
    def test_opening_raises(self, rig):
        laser = rig.laser
        rig.halt()
        for call in (
            lambda: laser.openShutter(),
            lambda: laser.openQSwitch(),
            lambda: laser.setChanHolding("shutter", 1),
            lambda: laser.setChanHolding("qSwitch", 1),
            lambda: laser.setChanHolding("pCell", 0.5),
        ):
            with pytest.raises(GlobalHaltException):
                call()
        assert laser.getChanHolding("shutter") == 0
        assert laser.getChanHolding("qSwitch") == 0
        assert laser.getChanHolding("pCell") == 0

    def test_closing_and_zeroing_stay_allowed(self, rig):
        laser = rig.laser
        laser.openShutter()
        laser.openQSwitch()
        laser.setChanHolding("pCell", 0.5)
        rig.halt()

        laser.closeShutter()
        laser.closeQSwitch()
        laser.setChanHolding("pCell", 0)

        assert laser.getChanHolding("shutter") == 0
        assert laser.getChanHolding("qSwitch") == 0
        assert laser.getChanHolding("pCell") == 0

    def test_reapplying_a_remembered_open_level_raises(self, rig):
        """``level=None`` re-applies the stored holding level; judge it on that."""
        laser = rig.laser
        laser.openShutter()  # remembered holding level for 'shutter' is now 1
        rig.halt()
        with pytest.raises(GlobalHaltException):
            laser.setChanHolding("shutter")
        laser.closeShutter()
        laser.setChanHolding("shutter")  # remembered level is 0 now: Allowed


# ---------------------------------------------------------------------------
# §6.1 Scanner
# ---------------------------------------------------------------------------


class TestScannerGuards:
    def test_opening_the_virtual_shutter_raises(self, rig):
        scanner = rig.scanner
        rig.halt()
        rig.daq.writes.clear()
        with pytest.raises(GlobalHaltException):
            scanner.setShutterOpen(True)
        assert rig.daq.writes == []
        assert scanner.getShutterOpen() is False

    def test_closing_the_virtual_shutter_stays_allowed(self, rig):
        scanner = rig.scanner
        scanner.setShutterOpen(True)
        rig.halt()
        rig.daq.writes.clear()
        scanner.setShutterOpen(False)
        assert rig.daq.writes == [("/Dev1/ao0", -4.0), ("/Dev1/ao1", -4.0)]

    def test_moving_the_mirrors_anywhere_else_raises(self, rig):
        scanner = rig.scanner
        scanner.setShutterOpen(True)
        rig.halt()
        rig.daq.writes.clear()
        with pytest.raises(GlobalHaltException):
            scanner.setCommand([1.0, 2.0])
        with pytest.raises(GlobalHaltException):
            scanner._setVoltage([1.0, 2.0])
        assert rig.daq.writes == []

    def test_starting_a_new_scan_raises(self, rig):
        scanner = rig.scanner
        task = ScannerTask(scanner, {"command": [1.0, 2.0]}, None)
        rig.halt()
        rig.daq.writes.clear()
        with pytest.raises(GlobalHaltException):
            task.configure()
        assert rig.daq.writes == []
        assert scanner._currentTask is None

    def test_configure_failure_after_publish_clears_current_task(self, rig):
        """A configure() failure that happens *after* publish must not leak.

        Unlike the halt guard above (refused before ``self.dev._currentTask =
        self``), an ordinary configure error -- e.g. no calibration on file for
        the requested laser -- is raised from inside the ``with self.dev.lock``
        block, after publish. A task that fails configure() is never added to
        ``Task.startedDevs``, so ``Task.abort()`` never calls this task's
        ``stop()`` to clear the slot; configure() has to clean up after itself.
        """
        scanner = rig.scanner
        task = ScannerTask(scanner, {"command": [1.0, 2.0], "laser": "Laser"}, None)
        with pytest.raises(Exception, match="not calibrated"):
            task.configure()
        # A scan that never started must not be handed to abort().
        assert scanner._currentTask is None

    def test_aborting_a_scan_in_progress_stays_allowed(self, rig):
        scanner = rig.scanner
        task = ScannerTask(scanner, {"command": [1.0, 2.0]}, None)
        task.configure()
        assert scanner._currentTask is task
        rig.halt()
        scanner.abort()  # aborts the scan and closes the virtual shutter
        assert scanner._currentTask is None
        assert scanner.getShutterOpen() is False


# ---------------------------------------------------------------------------
# §6.1 FilterWheel
# ---------------------------------------------------------------------------


class TestFilterWheelGuards:
    def test_starting_a_filter_move_raises(self, rig):
        fw = rig.filterWheel
        fw.setPosition(1)
        rig.halt()
        with pytest.raises(GlobalHaltException):
            fw.setPosition(0)
        assert fw.getPosition() == 1

    def test_stop_stays_allowed(self, rig):
        rig.filterWheel.setPosition(1)
        rig.halt()
        rig.filterWheel.stop()  # Allowed (§6.1) -- must not raise
        assert rig.filterWheel.getPosition() == 1


# ---------------------------------------------------------------------------
# §6.1 MotionPlanner
# ---------------------------------------------------------------------------


class _SpyPlanner(MotionPlanner):
    """Records whether planning happened; plans one AtomicMove per spec."""

    def __init__(self):
        MotionPlanner.__init__(self)
        self.planCalls = 0

    def plan(self, specs, name=""):
        self.planCalls += 1
        spec = specs[0]
        return AtomicMove(device=spec.device, position=spec.position, speed=spec.speed, explanation="test")


class TestMotionPlannerGuard:
    def test_execute_fails_the_task_before_reserving_devices(self, rig):
        """The refusal arrives as a failed task, NOT as a synchronous raise.

        execute() is decorated @asynch_with_qt_signals, so the guard runs inside
        the task body. Callers that wrap the *call* in except GlobalHaltException
        will never see it -- which is exactly the bug that reached a live rig via
        the Camera module's depth gauge (§9.2).
        """
        planner = _SpyPlanner()
        rig.halt()

        # Must not raise here. If this ever starts raising, §6.1/§9.2 and every
        # caller that connects a completion handler need revisiting.
        fut = planner.execute([MoveSpec(rig.stage, np.array([1e-3, 0.0, 0.0]), speed="fast")])

        with pytest.raises(GlobalHaltException):
            fut.wait(timeout=TIMEOUT)

        assert rig.manager.reserveCalls == [], "panic must never contend for device locks"
        assert planner.planCalls == 0
        assert rig.stage.stageThread.target is None


# ---------------------------------------------------------------------------
# §6.1 Manager / Task
# ---------------------------------------------------------------------------


class TestManagerGuards:
    def test_runTask_raises_before_building_the_task(self, rig):
        rig.halt()
        with pytest.raises(GlobalHaltException):
            rig.manager.runTask({"protocol": {"duration": 0.0}, "TaskDev": {}})
        assert rig.taskDevice.tasks == []

    def test_task_execute_raises_before_reserving_or_registering(self, rig):
        task = newTask(rig)
        rig.halt()
        with pytest.raises(GlobalHaltException):
            task.execute()
        devTask = rig.taskDevice.tasks[-1]
        assert devTask.configured is False and devTask.started is False
        assert rig.manager.reserveCalls == []
        assert list(rig.manager._tasksInProgress) == []

    def test_task_abort_and_stop_stay_allowed(self, rig):
        task = newTask(rig)
        task.execute(block=False)
        devTask = rig.taskDevice.tasks[-1]
        assert devTask.started is True
        rig.halt()
        task.abort()  # §6.1: Allowed
        assert devTask.stops == [True]
        task.stop()  # §6.1: Allowed
        assert list(rig.manager._tasksInProgress) == []


# ---------------------------------------------------------------------------
# §6.1 PatchPipetteStateManager
# ---------------------------------------------------------------------------


class TestStateManagerGuards:
    def test_starting_a_new_state_raises_and_changes_nothing(self, rig):
        sm = rig.stateManager
        sm.requestStateChange("bath")
        running = sm.currentJob
        assert running.started is True
        rig.halt()

        with pytest.raises(GlobalHaltException):
            sm.requestStateChange("bath")

        # No job built, the running job untouched, no fallback cascade.
        assert sm.currentJob is running
        assert running.stopped is False
        assert _FakeStateJob.instances == [running]
        assert rig.pipette.stateChanges == [(None, "bath")]

    def test_the_out_state_may_still_be_entered(self, rig):
        """§10.1: states fail to `out`, so `out` must remain reachable."""
        sm = rig.stateManager
        sm.requestStateChange("bath")
        rig.halt()
        job = sm.requestStateChange("out")
        assert isinstance(job, _OutJob) and job.started is True

    def test_stopping_the_running_job_stays_allowed(self, rig):
        sm = rig.stateManager
        sm.requestStateChange("bath")
        job = sm.currentJob
        rig.halt()
        sm.stopJob(allowNextState=False)
        assert job.stopped is True and job.cleanedUp is True


# ---------------------------------------------------------------------------
# §6.3 The halt-path contract
# ---------------------------------------------------------------------------


# The §5.2 participants, and the registered-callback name each one uses. This is
# the "what must be here" half of the contract; the "does it work" half is
# enforced by running whatever is actually in the registry, not this list.
EXPECTED_PARTICIPANTS = {
    "Stage.abort",
    "Pressure.abort",
    "Laser.abort",
    "Scanner.abort",
    "FilterWheel.abort",
    "Clamp.abort",
    "FakePipette.stateManager.abort",
    "Imager.abortTask",
    "Manager",
}


class TestHaltPathContract:
    """§6.3: every action in §5.2 must be Allowed in §6.1.

    Rather than restating §6.1's Allowed rows, these tests take the callbacks the
    rig actually registered and run them with the latch set. A guard added later
    that blocks a halt-path action fails here, named by its participant.
    """

    def _registerStateJob(self, rig):
        """Give the state manager a running job so it holds a registration (§10.1)."""
        rig.stateManager.requestStateChange("bath")

    def test_the_rig_registers_every_participant_in_5_2(self, rig):
        self._registerStateJob(rig)
        names = {name for name, _ in rig.globalHalt._abortCallbacks}
        missing = EXPECTED_PARTICIPANTS - names
        assert not missing, f"the contract test is not exercising: {sorted(missing)}"

    def test_every_registered_abort_callback_completes_while_halted(self, rig):
        """The contract itself: no callback trips a guard.

        Each participant is put in the state a panic would find it in -- moving,
        pressurised, shutter open, scanning, task running -- and then every
        callback in the registry is invoked with ``halted`` already True, exactly
        as the fan-out invokes it.
        """
        self._registerStateJob(rig)

        # Arrange the rig to be as un-safe as it can be.
        rig.stage.move([5e-3, 0, 0], speed=50e-6)
        rig.pressure.setPressure(source="regulator", pressure=30e3)
        rig.laser.openShutter()
        rig.laser.openQSwitch()
        rig.laser.setChanHolding("pCell", 0.7)
        rig.scanner.setShutterOpen(True)
        scannerTask = ScannerTask(rig.scanner, {"command": [1.0, 2.0]}, None)
        scannerTask.configure()
        task = newTask(rig)
        task.execute(block=False)

        callbacks = list(rig.globalHalt._abortCallbacks)
        assert len(callbacks) == len(EXPECTED_PARTICIPANTS)

        # Latch, then invoke each callback here rather than letting the fan-out do
        # it: same conditions (halted first, callback second) without nine threads
        # racing each other and this thread's assertions.
        rig.halt("contract check")

        failures = {}
        for name, cb in callbacks:
            try:
                cb()
            except Exception as exc:  # noqa: BLE001 -- the point is to report it
                failures[name] = exc
        assert not failures, f"abort callbacks blocked by a guard: {failures}"

        # ...and the rig really was made safe.
        assert rig.pressure.source == "atmosphere"
        assert rig.laser.getChanHolding("shutter") == 0
        assert rig.laser.getChanHolding("qSwitch") == 0
        assert rig.laser.getChanHolding("pCell") == 0
        assert rig.scanner.getShutterOpen() is False
        assert rig.taskDevice.tasks[-1].stops == [True]
        assert rig.imager.imagingThread.aborted is True
        assert rig.stateManager.currentJob.stopped is True

    def test_the_fanout_reports_no_self_inflicted_halt_exceptions(self, rig):
        """§5.3/§6.3 at runtime: a callback that trips its own guard is reported.

        Nothing must be reported here. This is the same check as the test above,
        but through the real fan-out rather than by calling the callbacks
        directly, so it also covers the callbacks running concurrently.
        """
        self._registerStateJob(rig)
        rig.pressure.setPressure(source="regulator", pressure=30e3)
        rig.laser.openShutter()
        rig.scanner.setShutterOpen(True)

        names = [name for name, _ in rig.globalHalt._abortCallbacks]
        with captured_thread_exceptions() as records:
            rig.globalHalt.halt("fan-out check")
            # Wait for the rig to reach its safe state, then a moment longer for
            # any late report to land.
            deadline = time.perf_counter() + TIMEOUT
            while time.perf_counter() < deadline and not (
                rig.pressure.source == "atmosphere"
                and rig.laser.getChanHolding("shutter") == 0
                and rig.scanner.getShutterOpen() is False
            ):
                time.sleep(0.01)
            time.sleep(0.3)
            reports = [
                str(r.exc_value) for r in list(records)
                if any(name in str(r.exc_value) for name in names)
            ]
        assert reports == []
        # ...and the fan-out really did run: an empty report list would otherwise
        # prove nothing.
        assert rig.pressure.source == "atmosphere"
        assert rig.laser.getChanHolding("shutter") == 0
        assert rig.scanner.getShutterOpen() is False

    def test_a_guard_that_blocked_the_halt_path_would_be_caught(self, rig):
        """The contract test can fail: break one guard and watch it report.

        Without this, ``test_every_registered_abort_callback_completes_while_halted``
        could pass because nothing was really exercised.
        """
        self._registerStateJob(rig)
        callbacks = list(rig.globalHalt._abortCallbacks)
        rig.halt("negative control")

        # Make PressureControl's guard non-directional, as a careless edit would.
        with mock.patch.object(PressureControl, "_isSafeWhileHalted", return_value=False):
            failures = {}
            for name, cb in callbacks:
                try:
                    cb()
                except Exception as exc:  # noqa: BLE001
                    failures[name] = exc
        assert "Pressure.abort" in failures
        assert isinstance(failures["Pressure.abort"], GlobalHaltException)


# ---------------------------------------------------------------------------
# §12 -- known, accepted conflicts between a halt-path handler and a guard
# ---------------------------------------------------------------------------


class TestAcceptedConflicts:
    def test_a_cleanup_handler_that_moves_cannot_break_the_fanout(self, rig):
        """§12 item 7: ``NucleusCollectState._cleanup()`` moves the manipulator.

        ``pip.dm.move()`` is refused while HALTED, which is correct -- but the
        call is inside ``log_and_ignore_exception``, so it cannot escape into the
        abort callback. This asserts that containment rather than the move.
        """
        from acq4.util.debug import log_and_ignore_exception

        rig.halt()
        reached = False
        with log_and_ignore_exception(Exception, "cleanup move"):
            rig.stage.move([1e-3, 0, 0], speed="fast")
            reached = True  # not reached: move() raises
        assert reached is False, "the guard must refuse the move"
        # ...and the refusal did not escape the wrapper: we are still running.

    def test_restoring_a_daq_holding_level_is_refused_but_contained(self, rig):
        """A task that holds a laser channel open cannot re-open it on the way out.

        ``DAQGenericTask.stop()`` restores each output channel to its holding
        level, which for an open shutter is an energising write and is refused.
        ``Task.stop()`` logs and moves on, so ``Manager.abortAllTasks()`` -- the
        §5.2 action -- still completes; only this one device task reports.
        """
        rig.laser.openShutter()  # the channel's remembered holding level is now 1
        laserTask = rig.laser.createTask({}, None)
        rig.halt()
        with pytest.raises(GlobalHaltException):
            laserTask.stop(abort=True)

        # Inside a Manager Task, that failure is caught and the abort completes.
        task = newTask(rig)
        task.tasks["Laser"] = laserTask
        task.startedDevs.append("Laser")
        task.abort()
        assert task.stopped is True
