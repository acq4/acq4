"""Tests for the plain-function device actions (go_*, focus_*, new_pipette, find_tip,
find_surface, sonicate, cellfie, verify_cell, run_task): fakes prove the right
device calls happen in order."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, OrchestrationError, TrackingLost
from acq4.experiment.actions.device import (
    go_home,
    go_park,
    go_search,
    go_approach,
    go_target,
    go_above_target,
    focus_tip,
    focus_target,
    new_pipette,
    find_tip,
    find_surface,
    sonicate,
    cellfie,
    verify_cell,
    run_task,
    load_preset,
)
from acq4.experiment.actions import device as device_mod
from acq4.util import Qt

# verify_cell reaches acq4_automation twice at call time: for CellTrackingLost, and
# for DEFORMATION_TOLERANCE by way of AutomationDebug.feature_tracking. That package
# is internal and is not a declared dependency, so the tests that actually call
# verify_cell only run where it is installed. Everything else in this module --
# cellfie included, now that it only captures a z-stack -- runs everywhere.
_TRACKER_SKIP_REASON = "verify_cell needs acq4_automation, an internal package"


class _Waitable:
    """Stand-in for the Future-like object real device calls return: .wait()
    records that it was awaited, and can be made to raise on wait()."""

    def __init__(self, error=None):
        self.error = error
        self.waited = False
        self.wait_timeout = None

    def wait(self, timeout=None):
        self.waited = True
        self.wait_timeout = timeout
        if self.error is not None:
            raise self.error
        return self


class FakePipetteDevice:
    def __init__(self, order):
        self.order = order
        self.move_calls = []
        self.move_error = None
        self.find_tip_error = None
        self.find_tip_calls = 0
        self.target_position = (1.0, 2.0, 3.0)
        # Park bookkeeping: what isParked() should answer, and the circle each
        # park was asked for.
        self.parked = False
        self.park_calls = []
        self.park_error = None
        self.home_position = (0.0, 0.0, 0.0)
        self.global_position = (1.0, 2.0, 3.0)

    def isParked(self, center=None, radius=None, height=None):
        return self.parked

    def goPark(self, speed="fast", center=None, radius=None, height=None):
        self.park_calls.append((speed, center, radius, height))
        self.order.append(("park", speed, center, radius))
        return _Waitable(self.park_error)

    def homePosition(self):
        if self.home_position is None:
            raise RuntimeError("no home position defined")
        return self.home_position

    def globalPosition(self):
        return self.global_position

    def moveTo(self, position, speed):
        self.move_calls.append((position, speed))
        self.order.append(("move", position, speed))
        return _Waitable(self.move_error)

    def iterativelyFindTip(self):
        self.find_tip_calls += 1
        self.order.append(("find_tip",))
        if self.find_tip_error is not None:
            raise self.find_tip_error

    def targetPosition(self):
        return self.target_position


class FakeClampDevice:
    def __init__(self, order, name="Clamp1"):
        self.order = order
        self._name = name
        self.offset_calls = 0

    def autoPipetteOffset(self):
        self.offset_calls += 1
        self.order.append(("offset",))

    def name(self):
        return self._name


class FakeScope:
    def __init__(self, depth=42.0, error=None):
        self.depth = depth
        self.error = error
        self.calls = []
        self.presets = {}
        self.preset_calls = []

    def findSurfaceDepth(self, imager):
        self.calls.append(imager)
        if self.error is not None:
            raise self.error
        return self.depth

    def loadPreset(self, name):
        conf = self.presets[name]  # raises bare KeyError for an unknown name, like the real device
        self.preset_calls.append(name)
        return conf


class FakeSonicator:
    def __init__(self, protocols=None, error=None):
        # Keyed by name like the real Sonicator's `protocols` config dict.
        self.protocols = {"clean": {}, "quick clean": {}} if protocols is None else protocols
        self.error = error
        self.calls = []
        self.wait_timeouts = []
        # If True, the task's wait() raises TimeoutError and leaves it running.
        self.wedged = False
        # Task returned by the last doProtocol() call.
        self.last_task = None
        # Pressure as observed at the moment the crystal was driven, recorded by
        # the fake pressure device below. This is the thing the pressure
        # bracketing exists for, so the tests assert on it rather than only on
        # the order of the setPressure calls.
        self.pressure_during = None
        self.pressureDevice = None

    def doProtocol(self, protocol):
        self.calls.append(protocol)
        if self.pressureDevice is not None:
            self.pressure_during = (
                self.pressureDevice.source,
                self.pressureDevice.pressure,
            )
        self.last_task = _SonicationTask(self)
        return self.last_task


class _SonicationTask:
    """Fake of the task Sonicator.doProtocol returns.

    `running` stays True after a timed-out wait() until stop() is called.
    """

    def __init__(self, sonicator):
        self.sonicator = sonicator
        self.running = True
        self.stops = []

    def wait(self, timeout=None):
        self.sonicator.wait_timeouts.append(timeout)
        if self.sonicator.error is not None:
            self.running = False
            raise self.sonicator.error
        if self.sonicator.wedged:
            raise TimeoutError(f"timed out after {timeout}s waiting for {self!r}")
        self.running = False
        return self

    def stop(self, reason=None, wait=False):
        self.stops.append((reason, wait))
        self.running = False


class FakePressureControl:
    def __init__(self, source="atmosphere", pressure=0.0):
        self.source = source
        self.pressure = pressure
        self.calls = []

    def getSource(self):
        return self.source

    def getPressure(self):
        return self.pressure

    def setPressure(self, source=None, pressure=None):
        self.calls.append((source, pressure))
        if source is not None:
            self.source = source
        if pressure is not None:
            self.pressure = pressure


class FakePipette:
    def __init__(self):
        self.order = []
        self.pipetteDevice = FakePipetteDevice(self.order)
        self.clampDevice = FakeClampDevice(self.order)
        self.focus_calls = []
        self.focus_error = None
        self.new_pipette_error = None
        self.new_pipette_calls = 0
        self.scope = FakeScope()
        self.imager = object()
        self.pressureDevice = FakePressureControl()
        self.sonicatorDevice = FakeSonicator()
        self.sonicatorDevice.pressureDevice = self.pressureDevice
        # The FSM seam go_park reads and writes: a name (None for "no state
        # running"), the states it was asked to enter, and an optional failure.
        self.state_name = "bath"
        self.set_state_calls = []
        self.set_state_error = None
        # The cell the orchestrator hands over before a protocol runs; kept the
        # way PatchPipette keeps it.
        self.cell = None
        self.setCell_calls = []

    def setCell(self, cell, target=True):
        self.setCell_calls.append((cell, target))
        self.cell = cell

    def getState(self):
        if self.state_name is None:
            return None
        job = type("FakeStateJob", (), {})()
        job.stateName = self.state_name
        return job

    def setState(self, state, **config):
        self.set_state_calls.append(state)
        self.order.append(("set_state", state))
        if self.set_state_error is not None:
            raise self.set_state_error
        self.state_name = state

    def name(self):
        return "PatchPipette1"

    def focusOnTip(self, speed):
        self.focus_calls.append(("tip", speed))
        return _Waitable(self.focus_error)

    def focusOnTarget(self, speed):
        self.focus_calls.append(("target", speed))
        return _Waitable(self.focus_error)

    def newPipette(self):
        self.new_pipette_calls += 1
        return _Waitable(self.new_pipette_error)

    def scopeDevice(self):
        return self.scope

    def imagingDevice(self):
        return self.imager


class FakeDir:
    def __init__(self):
        self.get_dir_calls = []

    def getDir(self, name, create=False):
        self.get_dir_calls.append((name, create))
        return f"dir:{name}"


class FakeManager:
    def __init__(self):
        self.current_dir = FakeDir()
        self.modules = {}

    def getCurrentDir(self):
        return self.current_dir

    def listInterfaces(self, iface):
        assert iface == "taskRunnerModule"
        return list(self.modules.keys())

    def getModule(self, name):
        return self.modules[name]


class FakeTaskRunnerModule(Qt.QObject):
    sigNewFrame = Qt.Signal(object)

    def __init__(self, docks, period=1.0, totalParams=5):
        super().__init__()
        self.docks = docks
        self.sequenceInfo = {"period": period, "totalParams": totalParams}
        self.run_calls = []
        self.run_error = None
        # Frames the run emits, standing in for the real module's per-sweep
        # sigNewFrame; and the directory handle run_task reads the saved
        # sequence's name off, mirroring TaskRunner.lastSequenceDir.
        self.frames = []
        self.lastSequenceDir = _FakeSequenceDir("protocol_000")

    def runSequence(self, store=True):
        self.run_calls.append(store)
        for frame in self.frames:
            self.sigNewFrame.emit(frame)
        return _Waitable(self.run_error)


class _FakeSequenceDir:
    def __init__(self, name):
        self._name = name

    def shortName(self):
        return self._name


class _FakeObjectStack:
    def __init__(self, data):
        self.data = data


class _FakeMotionEstimator:
    def __init__(self, data):
        self.original_object_stack = _FakeObjectStack(data)


class _FakeTracker:
    """Stands in for the acq4_automation tracker verify_cell initializes: exposes
    the one attribute chain the details payload reads."""

    def __init__(self, data):
        self.motion_estimator = _FakeMotionEstimator(data)


class FakeCell:
    def __init__(self):
        self.tracker_calls = []
        self.tracker_kwargs = []
        self.tracker_error = None
        self.tracker_stack = None

    def initializeTracker(self, imager, use_cellpose=False, **tracker_kwargs):
        # Mirror Cell.initializeTracker's **tracker_kwargs passthrough so callers can
        # forward tracker settings without this double having to know each one.
        self.tracker_calls.append((imager, use_cellpose))
        # Recorded before the error path, so a test asserting on a lost cell can
        # still see what the call was made with.
        self.tracker_kwargs.append(tracker_kwargs)
        # Mirrors the real Cell.initializeTracker: a freshly-built tracker is
        # assigned to _tracker before verify_reference() can raise
        # CellTrackingLost, so a reference that fails to verify still leaves a
        # tracker (and its stack) behind for the caller to read.
        if self.tracker_stack is not None:
            self._tracker = _FakeTracker(self.tracker_stack)
        if self.tracker_error is not None:
            raise self.tracker_error


@pytest.fixture
def pip():
    return FakePipette()


@pytest.fixture
def ctx(pip):
    return ExecutionContext(pipette=pip, manager=FakeManager(), cell=FakeCell())


def _entry_names(ctx):
    names = []
    ctx.on_log_action = lambda action_entry: names.append(action_entry.name)
    return names


# -- named moves --------------------------------------------------------


@pytest.mark.parametrize(
    "fn, name, position",
    [
        (go_home, "Pipette To Home", "home"),
        (go_search, "Pipette To Search Position", "search"),
        (go_approach, "Pipette To Approach Position", "approach"),
        (go_target, "Pipette To Target", "target"),
        (go_above_target, "Pipette To Above Target", "aboveTarget"),
    ],
)
def test_named_move_calls_pipette_device_move_to_and_waits(ctx, pip, fn, name, position):
    names = _entry_names(ctx)

    fn(ctx, speed="slow")

    assert pip.pipetteDevice.move_calls == [(position, "slow")]
    assert names == [name]


def test_named_move_defaults_to_fast_speed(ctx, pip):
    go_home(ctx)

    assert pip.pipetteDevice.move_calls == [("home", "fast")]


# -- focus ----------------------------------------------------------------


def test_focus_tip_dispatches_to_focus_on_tip(ctx, pip):
    names = _entry_names(ctx)

    focus_tip(ctx, speed="slow")

    assert pip.focus_calls == [("tip", "slow")]
    assert names == ["Focus On Pipette Tip"]


def test_focus_target_dispatches_to_focus_on_target(ctx, pip):
    names = _entry_names(ctx)

    focus_target(ctx, speed="slow")

    assert pip.focus_calls == [("target", "slow")]
    assert names == ["Focus On Target"]


# -- new_pipette ------------------------------------------------------------


def test_new_pipette_calls_new_pipette_and_waits(ctx, pip):
    names = _entry_names(ctx)

    new_pipette(ctx)

    assert pip.new_pipette_calls == 1
    assert names == ["New Pipette Calibration"]


def test_new_pipette_wraps_failure_as_orchestration_error(ctx, pip):
    pip.new_pipette_error = RuntimeError("boom")

    with pytest.raises(OrchestrationError) as excinfo:
        new_pipette(ctx)

    assert "New Pipette Calibration" in str(excinfo.value)
    assert "boom" in str(excinfo.value)


# -- find_tip -----------------------------------------------------------


def test_find_tip_calls_steps_in_order(ctx, pip):
    names = _entry_names(ctx)

    find_tip(ctx)

    assert pip.order == [
        ("offset",),
        ("find_tip",),
    ]
    assert names == ["Find Pipette Tip"]


def test_find_tip_does_not_move_the_pipette(ctx, pip):
    """find_tip calibrates where the pipette already is. Positioning is the
    caller's job (go_search, go_above_target), so a protocol can find the tip in
    whichever field it wants without the action second-guessing it."""
    find_tip(ctx)

    assert pip.pipetteDevice.move_calls == []


def test_find_tip_wraps_failure_as_orchestration_error(ctx, pip):
    pip.pipetteDevice.find_tip_error = RuntimeError("no tip")

    with pytest.raises(OrchestrationError) as excinfo:
        find_tip(ctx)

    assert "Find Pipette Tip" in str(excinfo.value)
    assert "no tip" in str(excinfo.value)


# -- find_surface -------------------------------------------------------


def test_find_surface_returns_depth(ctx, pip):
    names = _entry_names(ctx)
    pip.scope.depth = 123.4

    result = find_surface(ctx)

    assert result == 123.4
    assert pip.scope.calls == [pip.imager]
    assert names == ["Find Sample Surface"]


def test_find_surface_wraps_value_error(ctx, pip):
    pip.scope.error = ValueError("no surface")

    with pytest.raises(OrchestrationError) as excinfo:
        find_surface(ctx)

    assert "Find Sample Surface" in str(excinfo.value)
    assert "no surface" in str(excinfo.value)


# -- cellfie --------------------------------------------------------------


def test_cellfie_focuses_and_saves_the_zstack(ctx, pip, monkeypatch):
    """No importorskip here, deliberately: cellfie captures a z-stack and
    nothing else, so it never reaches acq4_automation and this must pass where
    that package is not installed."""
    names = _entry_names(ctx)
    pip.pipetteDevice.target_position = (0.0, 0.0, 100e-6)
    calls = []

    def fake_run_image_sequence(imager, z_stack=None, storage_dir=None, name=None):
        calls.append(
            dict(imager=imager, z_stack=z_stack, storage_dir=storage_dir, name=name)
        )
        return _Waitable()

    monkeypatch.setattr(device_mod, "run_image_sequence", fake_run_image_sequence)

    cellfie(ctx, height=30e-6, step=1e-6)

    assert pip.focus_calls == [("target", "fast")]
    assert len(calls) == 1
    call = calls[0]
    assert call["imager"] is pip.imager
    start, end, step = call["z_stack"]
    assert start == pytest.approx(100e-6 - 15e-6)
    assert end == pytest.approx(start + 30e-6)
    assert step == 1e-6
    assert call["storage_dir"] == "dir:cellfie"
    assert call["name"] == "cellfie"
    assert names == ["Cellfie"]


def test_cellfie_does_not_touch_the_cell_tracker(ctx, pip, monkeypatch):
    """The tracker's reference-and-re-find check is verify_cell's job: the
    tracker acquires its own stack rather than reading the one saved here, so a
    cellfie must leave the cell's tracker alone."""
    pip.pipetteDevice.target_position = (0.0, 0.0, 100e-6)
    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())

    cellfie(ctx)

    assert ctx.cell.tracker_calls == []


def test_cellfie_shows_no_tracker_stack_in_its_details(ctx, pip, monkeypatch):
    # A cell carries its tracker across passes, so one may already hold a
    # reference stack. Showing that as a cellfie's details would present a
    # tracker crop as the stack this action just saved to disk.
    import numpy as np

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell._tracker = _FakeTracker(np.ones((3, 4, 5)))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert details == []


def test_cellfie_default_height_and_step(ctx, pip, monkeypatch):
    pip.pipetteDevice.target_position = (0.0, 0.0, 100e-6)
    calls = []
    monkeypatch.setattr(
        device_mod,
        "run_image_sequence",
        lambda imager, z_stack=None, storage_dir=None, name=None: (
            calls.append(z_stack) or _Waitable()
        ),
    )

    cellfie(ctx)

    start, end, step = calls[0]
    assert step == 1e-6
    assert end - start == pytest.approx(30e-6)


# -- verify_cell ----------------------------------------------------------


def _verify_cell_context(tissue_moved_hook=None):
    """An ExecutionContext wired for verify_cell.

    FakePipette, FakeManager, and FakeCell already cover everything verify_cell
    touches -- the tracker acquires its own imaging, so there is no z-stack save
    to stub out here -- so this only wires them together.
    """
    return ExecutionContext(
        cell=FakeCell(),
        pipette=FakePipette(),
        manager=FakeManager(),
        tissue_moved_hook=tissue_moved_hook,
    )


def test_verify_cell_initializes_the_tracker(ctx, pip):
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    names = _entry_names(ctx)

    verify_cell(ctx)

    assert ctx.cell.tracker_calls == [(pip.imager, True)]
    # Whichever call site initializes a cell's tracker fixes its deformation tolerance
    # for that cell's lifetime, so this one has to forward it too.
    # Read from the constant's own module rather than through device.py: verify_cell
    # imports it inside the function body, so it is not an attribute of that module.
    from acq4.modules.AutomationDebug.feature_tracking import DEFORMATION_TOLERANCE

    assert ctx.cell.tracker_kwargs == [
        {"deformation_tolerance": DEFORMATION_TOLERANCE, "segmenter": None}
    ]
    assert names == ["Verify Cell"]


def test_verify_cell_needs_no_focus_or_zstack_of_its_own(ctx, pip, monkeypatch):
    """The tracker's own acquisition moves the imager (_take_stackshot), so this
    action neither focuses the scope nor saves a z-stack of its own: the focus
    and the cellfie/ save belong to the action that does."""
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    saves = []
    monkeypatch.setattr(
        device_mod,
        "run_image_sequence",
        lambda *a, **k: (saves.append((a, k)) or _Waitable()),
    )

    verify_cell(ctx)

    assert pip.focus_calls == []
    assert saves == []


def test_verify_cell_tracks_with_the_configured_segmenter(ctx, monkeypatch):
    """Tracking has to segment with the same checkpoint detection uses; on stock
    cpsam it finds no cells in a tracking crop at all."""
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    monkeypatch.setattr(device_mod, "segmenter_path", lambda: "/models/tuned")

    verify_cell(ctx)

    assert ctx.cell.tracker_kwargs[0]["segmenter"] == "/models/tuned"


def test_verify_cell_routes_a_lost_cell_to_the_tissue_moved_hook():
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    seen = []

    def hook(ctx, reason):
        seen.append(reason)
        ctx.next_cell()

    ctx = _verify_cell_context(tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features matched")

    with pytest.raises(AdvanceToNextCell):
        verify_cell(ctx)
    assert seen == ["no features matched"]


def test_verify_cell_lets_an_unrelated_valueerror_propagate():
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    # Only the named class is tissue motion. A bare ValueError out of the
    # tracker stack is a bug, and classifying it as motion would trigger a
    # destructive rescan whose prompt defaults to "Rescan".
    called = []
    ctx = _verify_cell_context(tissue_moved_hook=lambda c, r: called.append(r))
    ctx.cell.tracker_error = ValueError("something else entirely")

    with pytest.raises(ValueError, match="something else entirely"):
        verify_cell(ctx)
    assert called == []


def test_verify_cell_with_no_hook_raises_trackinglost():
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    ctx = _verify_cell_context()
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features")

    with pytest.raises(TrackingLost):
        verify_cell(ctx)


# -- run_task -------------------------------------------------------------


def test_run_task_finds_module_by_clamp_name_and_runs(ctx, pip, monkeypatch):
    names = _entry_names(ctx)
    pip.clampDevice._name = "Clamp1"
    mod = FakeTaskRunnerModule(docks={"Clamp1": object()})
    ctx.manager.modules = {"TaskRunner": mod}

    monkeypatch.setattr(
        device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k)
    )

    run_task(ctx, store=False)

    assert mod.run_calls == [False]
    assert names == ["Task Runner Sequence"]


def test_run_task_timeout_defaults_from_sequence_length(ctx, pip, monkeypatch):
    mod = FakeTaskRunnerModule(docks={"Clamp1": object()}, period=2.0, totalParams=10)
    ctx.manager.modules = {"TaskRunner": mod}
    pip.clampDevice._name = "Clamp1"

    seen_waitable = {}

    def fake_run_in_gui_thread(fn, *a, **k):
        result = fn(*a, **k)
        seen_waitable["result"] = result
        return result

    monkeypatch.setattr(device_mod, "run_in_gui_thread", fake_run_in_gui_thread)

    run_task(ctx)

    # expected_duration = 2.0 * 10 = 20; max(30, 20 * 20) = 400
    assert seen_waitable["result"].wait_timeout == 400


def test_run_task_raises_when_no_module_matches(ctx, pip):
    pip.clampDevice._name = "Clamp1"
    ctx.manager.modules = {}

    with pytest.raises(OrchestrationError) as excinfo:
        run_task(ctx)

    assert "Task Runner Sequence" in str(excinfo.value)
    assert "Clamp1" in str(excinfo.value)


# -- load_preset ------------------------------------------------------------


def test_load_preset_applies_the_named_preset(ctx, pip):
    names = _entry_names(ctx)
    pip.scope.presets = {"GFP": {"camera": "GFP"}, "brightfield": {"camera": "brightfield"}}

    load_preset(ctx, "GFP")

    assert pip.scope.preset_calls == ["GFP"]
    assert names == ["Load Imaging Preset"]


def test_load_preset_none_is_a_silent_noop(ctx, pip):
    names = _entry_names(ctx)
    pip.scope.presets = {"GFP": {}}

    load_preset(ctx, None)

    assert pip.scope.preset_calls == []
    assert names == []


def test_load_preset_empty_string_is_also_a_silent_noop(ctx, pip):
    names = _entry_names(ctx)
    pip.scope.presets = {"GFP": {}}

    load_preset(ctx, "")

    assert pip.scope.preset_calls == []
    assert names == []


def test_load_preset_unknown_name_raises_orchestration_error_listing_available(ctx, pip):
    pip.scope.presets = {"GFP": {}, "brightfield": {}}

    with pytest.raises(OrchestrationError) as excinfo:
        load_preset(ctx, "nonexistent")

    assert "Load Imaging Preset" in str(excinfo.value)
    assert "GFP" in str(excinfo.value)
    assert "brightfield" in str(excinfo.value)


def test_load_preset_unknown_name_with_no_presets_configured_reads_sensibly(ctx, pip):
    # pip.scope.presets is already {} from the FakeScope fixture -- the mock
    # rig configures no presets, so this is what a typo'd name hits there.
    with pytest.raises(OrchestrationError) as excinfo:
        load_preset(ctx, "GFP")

    message = str(excinfo.value)
    assert "GFP" in message
    # No dangling "(available: )" -- say plainly that nothing is configured.
    assert "available:" not in message
    assert "no presets are configured" in message


# -- sonicate ---------------------------------------------------------------


def test_sonicate_runs_the_named_protocol(ctx, pip):
    names = _entry_names(ctx)

    sonicate(ctx, "quick clean")

    assert pip.sonicatorDevice.calls == ["quick clean"]
    assert names == ["Sonicate Pipette"]
    # No pressure asked for, so the regulator is never touched.
    assert pip.pressureDevice.calls == []


@pytest.mark.parametrize("protocol", [None, ""])
def test_sonicate_unconfigured_protocol_is_a_silent_noop(ctx, pip, protocol):
    """Empty skips the step outright -- the load_preset convention, and what
    lets a rig whose sonicator has no such protocol run the same protocol file
    unedited. Silent: no log entry either, so Area 5 does not show a step that
    was never asked for."""
    names = _entry_names(ctx)

    sonicate(ctx, protocol, pressure=50e3)

    assert pip.sonicatorDevice.calls == []
    assert pip.pressureDevice.calls == []
    assert names == []


def test_sonicate_holds_pressure_during_the_drive_and_restores_it_after(ctx, pip):
    pip.pressureDevice = FakePressureControl(source="atmosphere", pressure=0.0)
    pip.sonicatorDevice.pressureDevice = pip.pressureDevice

    sonicate(ctx, "quick clean", pressure=50e3, settle=0.0)

    # The point of the bracketing: the crystal ran with the regulator actually
    # charged, not merely with a setPressure call somewhere in the sequence.
    assert pip.sonicatorDevice.pressure_during == ("regulator", 50e3)
    assert pip.pressureDevice.calls == [("regulator", 50e3), ("atmosphere", 0.0)]


def test_sonicate_restores_the_source_and_setpoint_that_were_in_force(ctx, pip):
    """Read-then-restore, not restore-to-a-constant: a pipette left holding
    regulator pressure by its current FSM state gets that back, which is why
    the action reads both values before it writes."""
    pip.pressureDevice = FakePressureControl(source="regulator", pressure=-3e3)
    pip.sonicatorDevice.pressureDevice = pip.pressureDevice

    sonicate(ctx, "quick clean", pressure=50e3)

    assert pip.pressureDevice.calls[-1] == ("regulator", -3e3)


def test_sonicate_restores_pressure_when_the_sonication_fails(ctx, pip):
    """The restore is in a finally: a sonication that raises must not leave the
    regulator charged, and the original error must still be what propagates."""
    pip.sonicatorDevice.error = RuntimeError("overload")

    with pytest.raises(RuntimeError, match="overload"):
        sonicate(ctx, "quick clean", pressure=50e3)

    assert pip.pressureDevice.calls == [("regulator", 50e3), ("atmosphere", 0.0)]


def test_sonicate_reports_the_original_error_even_if_the_restore_also_fails(ctx, pip):
    """A failing restore is logged and swallowed rather than replacing the
    exception that caused it -- otherwise the operator would be told about the
    pressure device and never about the sonicator."""
    pip.sonicatorDevice.error = RuntimeError("overload")
    realSetPressure = pip.pressureDevice.setPressure

    # Fails only on the restore. Failing the opening pressurize instead would
    # test nothing here: that error is raised before the sonicator is ever
    # driven, so it is the only exception in flight and is rightly the one that
    # propagates.
    def failOnRestore(source=None, pressure=None):
        if pip.pressureDevice.calls:
            raise RuntimeError("pressure device offline")
        return realSetPressure(source=source, pressure=pressure)

    pip.pressureDevice.setPressure = failOnRestore

    with pytest.raises(RuntimeError, match="overload"):
        sonicate(ctx, "quick clean", pressure=50e3)


def test_sonicate_waits_with_a_bounded_timeout(ctx, pip):
    """An unbounded wait on a sonicator that never reports finished would park
    the run with the regulator charged."""
    sonicate(ctx, "quick clean")

    assert pip.sonicatorDevice.wait_timeouts == [device_mod._SONICATION_TIMEOUT]


def test_sonicate_stops_the_drive_when_the_wait_gives_up(ctx, pip):
    """A timed-out sonication wait stops the task with wait=True before raising."""
    pip.sonicatorDevice.wedged = True

    with pytest.raises(TimeoutError):
        sonicate(ctx, "quick clean")

    task = pip.sonicatorDevice.last_task
    assert not task.running
    assert [waited for _reason, waited in task.stops] == [True]


def test_sonicate_stops_the_drive_before_restoring_pressure(ctx, pip):
    """After a timed-out sonication wait, the task is stopped before pressure is restored."""
    pip.sonicatorDevice.wedged = True
    pip.pressureDevice = FakePressureControl(source="atmosphere", pressure=0.0)
    pip.sonicatorDevice.pressureDevice = pip.pressureDevice
    realSetPressure = pip.pressureDevice.setPressure
    sonicating = []

    def recordSetPressure(source=None, pressure=None):
        task = pip.sonicatorDevice.last_task
        sonicating.append(task is not None and task.running)
        return realSetPressure(source=source, pressure=pressure)

    pip.pressureDevice.setPressure = recordSetPressure

    with pytest.raises(TimeoutError):
        sonicate(ctx, "quick clean", pressure=50e3)

    # The last setPressure call is the restore; the first applies the sonication pressure.
    assert sonicating[-1] is False
    assert pip.pressureDevice.calls == [("regulator", 50e3), ("atmosphere", 0.0)]


def test_sonicate_unknown_protocol_raises_orchestration_error_listing_available(ctx, pip):
    """Checked here rather than passed through: doProtocol treats an
    unrecognized name as a literal protocol definition, so a typo would reach
    the DAQ as a malformed stimulus instead of naming the configured protocols."""
    with pytest.raises(OrchestrationError) as excinfo:
        sonicate(ctx, "quik clean")

    message = str(excinfo.value)
    assert "Sonicate Pipette" in message
    assert "quik clean" in message
    assert "quick clean" in message
    # And nothing was driven or pressurized on the way to the error.
    assert pip.sonicatorDevice.calls == []
    assert pip.pressureDevice.calls == []


def test_sonicate_unknown_protocol_with_none_configured_reads_sensibly(ctx, pip):
    pip.sonicatorDevice.protocols = {}

    with pytest.raises(OrchestrationError) as excinfo:
        sonicate(ctx, "quick clean")

    message = str(excinfo.value)
    assert "available:" not in message
    assert "no protocols are configured" in message


def test_sonicate_without_a_sonicator_device_raises_orchestration_error(ctx, pip):
    pip.sonicatorDevice = None

    with pytest.raises(OrchestrationError) as excinfo:
        sonicate(ctx, "quick clean")

    assert "no sonicatorDevice" in str(excinfo.value)
    assert "PatchPipette1" in str(excinfo.value)


def test_sonicate_asking_for_pressure_without_a_pressure_device_raises(ctx, pip):
    """Refused up front rather than sonicating dry: a protocol that asked for
    pressure at the tip did so for a reason, and silently dropping it would
    make a step that looks like it ran do something else."""
    pip.pressureDevice = None

    with pytest.raises(OrchestrationError) as excinfo:
        sonicate(ctx, "quick clean", pressure=50e3)

    assert "no pressureDevice" in str(excinfo.value)
    assert pip.sonicatorDevice.calls == []


def test_sonicate_without_pressure_needs_no_pressure_device(ctx, pip):
    """The pressure device is only required by the pressure option itself."""
    pip.pressureDevice = None

    sonicate(ctx, "quick clean")

    assert pip.sonicatorDevice.calls == ["quick clean"]


def test_sonicate_holds_pressure_through_the_settle_delay(ctx, pip, monkeypatch):
    """`settle` keeps expelling after the crystal stops, so the restore has to
    come after the sleep -- not between the drive and it."""
    order = []
    monkeypatch.setattr(device_mod, "sleep", lambda t: order.append(("sleep", t)))
    realSetPressure = pip.pressureDevice.setPressure

    def recordingSetPressure(source=None, pressure=None):
        order.append(("pressure", source, pressure))
        return realSetPressure(source=source, pressure=pressure)

    pip.pressureDevice.setPressure = recordingSetPressure

    sonicate(ctx, "quick clean", pressure=50e3, settle=4.0)

    assert order == [
        ("pressure", "regulator", 50e3),
        ("sleep", 4.0),
        ("pressure", "atmosphere", 0.0),
    ]


def test_sonicate_skips_the_settle_sleep_when_it_is_zero(ctx, pip, monkeypatch):
    slept = []
    monkeypatch.setattr(device_mod, "sleep", lambda t: slept.append(t))

    sonicate(ctx, "quick clean", pressure=50e3)

    assert slept == []


def test_verify_cell_retains_the_trackers_stack_as_an_image_stack_payload(ctx, pip):
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    import numpy as np

    ctx.cell.tracker_stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    verify_cell(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "image_stack"
    # Rows/cols swapped so it displays in the same orientation as the Camera
    # module, matching AutomationDebug's own cell stack view.
    assert payload["stack"].shape == (5, 3, 4)
    assert payload["center_index"] == 2
    assert payload["title"] == "Cell Tracker Reference"


def test_verify_cell_center_index_is_none_for_a_single_frame_stack(ctx, pip):
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    import numpy as np

    ctx.cell.tracker_stack = np.zeros((1, 4, 3))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    verify_cell(ctx)

    assert details[0][1]["center_index"] is None


def test_verify_cell_sets_no_payload_when_the_tracker_exposes_no_stack(ctx, pip):
    # A cell whose tracker did not expose a stack must not make verify_cell
    # raise out of the orchestrator's worker thread over a display concern.
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    ctx.cell.tracker_stack = None
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    verify_cell(ctx)

    assert details == []


def test_verify_cell_retains_the_stack_when_the_cell_is_lost():
    # A stack was genuinely recorded before verify_reference rejected it, so the
    # operator must still see it even though tissue_moved never returns. Not
    # showing it would misrepresent a stack that exists as a stack that doesn't.
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    import numpy as np
    from acq4_automation.feature_tracking import CellTrackingLost

    def hook(c, reason):
        raise AdvanceToNextCell(reason)

    ctx = _verify_cell_context(tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("gone")
    ctx.cell.tracker_stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    with pytest.raises(AdvanceToNextCell):
        verify_cell(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "image_stack"
    assert payload["stack"].shape == (5, 3, 4)
    assert payload["center_index"] == 2
    # Titled distinctly from the success path so the operator isn't misled into
    # thinking the reference actually verified.
    assert payload["title"] == "Cell Tracker Reference (did not match)"


def test_verify_cell_sets_no_payload_when_the_cell_is_lost_with_no_tracker_at_all():
    # initializeTracker can fail before a tracker ever gets built (e.g. the
    # tracker constructor itself raises CellTrackingLost). No tracker means no
    # stack to show, and that must not crash the details attachment.
    pytest.importorskip("acq4_automation", reason=_TRACKER_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    def hook(c, reason):
        raise AdvanceToNextCell(reason)

    ctx = _verify_cell_context(tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("gone")
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    with pytest.raises(AdvanceToNextCell):
        verify_cell(ctx)

    assert details == []


# -- run_task: sweep retention -------------------------------------------


class _FakeMetaArray:
    """Stands in for a clamp device's task result: indexable by channel name,
    with an xvals('Time') axis, the shape MultiClamp's task GUI reads."""

    def __init__(self, times, primary):
        self._times = times
        self._primary = primary

    def __getitem__(self, key):
        assert key == "primary"
        return self._primary

    def xvals(self, axis):
        assert axis == "Time"
        return self._times


def _sequence_frame(clampName, times, primary, params=None):
    return {"result": {clampName: _FakeMetaArray(times, primary)}, "params": params or {}}


def test_decimate_leaves_a_short_trace_alone():
    import numpy as np

    t = np.linspace(0, 1, 100)
    times, values, factor = device_mod._decimate(t, t * 2.0, maxPoints=4000)

    assert factor == 1
    assert len(times) == 100
    assert np.array_equal(values, t * 2.0)


def test_decimate_reduces_a_long_trace_and_reports_the_factor():
    import numpy as np

    t = np.linspace(0, 1, 40000)
    times, values, factor = device_mod._decimate(t, t, maxPoints=4000)

    assert factor == 10
    assert len(times) == len(values) == 4000


def test_run_task_retains_each_sweep_as_a_task_results_payload(ctx, pip, monkeypatch):
    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    t = np.linspace(0, 1, 10)
    module.frames = [
        _sequence_frame(clampName, t, t * 1.0),
        _sequence_frame(clampName, t, t * 2.0),
    ]

    run_task(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "task_results"
    assert len(payload["traces"]) == 2
    assert payload["decimation"] == 1
    assert np.array_equal(payload["traces"][1][1], t * 2.0)


def test_run_task_payload_names_the_sequence_directory(ctx, pip, monkeypatch):
    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    module.lastSequenceDir = _FakeSequenceDir("protocol_003")
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    module.frames = []

    run_task(ctx)

    assert details[0][1]["sequence_dir"] == "protocol_003"


def test_run_task_retains_nothing_but_still_reports_when_no_sweeps_arrive(ctx, pip, monkeypatch):
    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    module.frames = []

    run_task(ctx)

    assert details[0][1]["traces"] == []


def test_run_task_retains_its_sweeps_even_when_the_sequence_raises(ctx, pip, monkeypatch):
    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    module.run_error = RuntimeError("amplifier fell over")
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    t = np.linspace(0, 1, 10)
    module.frames = [_sequence_frame(clampName, t, t)]

    with pytest.raises(RuntimeError):
        run_task(ctx)

    assert len(details[0][1]["traces"]) == 1


def test_run_task_decimation_reports_the_largest_factor_across_sweeps(ctx, pip, monkeypatch):
    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    short = np.linspace(0, 1, 100)
    long = np.linspace(0, 1, 40000)
    module.frames = [
        _sequence_frame(clampName, short, short),
        _sequence_frame(clampName, long, long),
    ]

    run_task(ctx)

    assert details[0][1]["decimation"] == 10
    assert len(details[0][1]["traces"]) == 2


def test_find_surface_retains_the_detected_depth(ctx, pip):
    pip.scope.depth = -1.2e-3
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    depth = find_surface(ctx)

    assert depth == -1.2e-3
    kind, payload = details[0]
    assert kind == "text"
    assert "surface" in payload["lines"][0]
    assert "1.2 mm" in payload["lines"][0]


def test_find_surface_retains_nothing_when_detection_fails(ctx, pip):
    pip.scope.error = ValueError("no surface found")
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    with pytest.raises(OrchestrationError):
        find_surface(ctx)

    assert details == []


# -- run_task: thread affinity ----------------------------------------------


def test_run_task_collects_sweeps_when_driven_from_a_worker_thread(qapp, qtbot, pip):
    """run_task runs on the orchestrator's worker thread -- a gentletask
    ThreadTask with no Qt event loop -- while TaskRunner.sigNewFrame is emitted
    on the GUI thread. PyQt gives a plain callable slot the affinity of the
    thread that called connect(), so the subscription has to be established on
    the GUI thread; made from the worker, every frame would be queued to a loop
    that never runs and the payload would report no sweeps at all.

    Genuinely cross-thread on purpose: driven from a worker while this (GUI)
    thread pumps and emits. run_in_gui_thread is deliberately left unpatched.
    """
    import threading

    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx = ExecutionContext(pipette=pip, manager=FakeManager(), cell=FakeCell())
    ctx.manager.modules["TaskRunner"] = module
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    t = np.linspace(0, 1, 10)
    module.frames = [
        _sequence_frame(clampName, t, t * 1.0),
        _sequence_frame(clampName, t, t * 2.0),
    ]
    done = threading.Event()
    ranOn = {}

    def runOnWorker():
        try:
            ranOn["thread"] = Qt.QtCore.QThread.currentThread()
            run_task(ctx, store=False)
        finally:
            done.set()

    worker = threading.Thread(target=runOnWorker, name="run-task-driver")
    worker.start()
    # This thread has to keep pumping: run_task marshals both its subscription
    # and runSequence itself here through run_in_gui_thread.
    qtbot.waitUntil(done.is_set, timeout=5000)
    worker.join(5)

    assert ranOn["thread"] is not Qt.QtCore.QThread.currentThread()
    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "task_results"
    assert len(payload["traces"]) == 2
    assert np.array_equal(payload["traces"][1][1], t * 2.0)


# -- go_park -----------------------------------------------------------------
#
# The action that gets the tip out of the slice the moment it stops being
# needed there. What these pin down is the decision table around the move, not
# the geometry -- where the park position actually is belongs to Pipette
# (see acq4/devices/Pipette/tests/test_park_position.py).


def _parkCtx(circle=((0.0, 0.0), 300e-6), state="bath"):
    pip = FakePipette()
    pip.state_name = state
    ctx = ExecutionContext(pipette=pip)
    ctx.occlusion_circle = lambda: circle
    return ctx, pip


def test_go_park_retracts_clear_of_the_circle_the_context_names():
    ctx, pip = _parkCtx(circle=((4e-3, 5e-3), 300e-6))
    pip.pipetteDevice.parked = False

    go_park(ctx)

    assert pip.pipetteDevice.park_calls == [("fast", (4e-3, 5e-3), 300e-6, None)]


def test_go_park_prefers_an_explicitly_given_circle_over_the_contexts():
    """A protocol that knows better than the queue -- staying clear of something
    the orchestrator has no record of -- must not have its circle ignored."""
    ctx, pip = _parkCtx(circle=((0.0, 0.0), 300e-6))

    go_park(ctx, center=(1e-3, 1e-3), radius=750e-6)

    assert pip.pipetteDevice.park_calls == [("fast", (1e-3, 1e-3), 750e-6, None)]


def test_go_park_goes_to_bath_before_retracting():
    """Approach, cell detect, contact cell and clean all drive the manipulator
    themselves. Retracting out from under one of them is two callers moving one
    device, so the state is left first -- and the order matters, not just that
    both happened."""
    ctx, pip = _parkCtx(state="cell detect")

    go_park(ctx)

    assert pip.order == [("set_state", "bath"), ("park", "fast", (0.0, 0.0), 300e-6)]


def test_go_park_leaves_a_pipette_already_in_bath_alone():
    ctx, pip = _parkCtx(state="bath")

    go_park(ctx)

    assert pip.set_state_calls == []
    assert len(pip.pipetteDevice.park_calls) == 1


def test_go_park_ends_a_whole_cell_recording_rather_than_leaving_the_tip_on_it():
    """The deliberate trade, stated as a test so it cannot be changed silently:
    by the time anything asks for a park the protocol is done with the cell, and
    the alternative on the rig is the tip staying on it -- in the slice, in the
    light path -- until the next cell's clean cycle retracts it."""
    ctx, pip = _parkCtx(state="whole cell")

    go_park(ctx)

    assert pip.set_state_calls == ["bath"]
    assert len(pip.pipetteDevice.park_calls) == 1


@pytest.mark.parametrize("state", ["out", "clean", "refill", "collect", "home with nucleus"])
def test_go_park_does_nothing_to_a_tip_that_is_not_in_the_chamber(state):
    """These states put the tip somewhere else on the rig entirely. Parking one
    would drive it back across to the chamber, and 'bath' would charge a
    well-bound pipette with bath pressure where there is no bath."""
    ctx, pip = _parkCtx(state=state)

    go_park(ctx)

    assert pip.set_state_calls == []
    assert pip.pipetteDevice.park_calls == []


@pytest.mark.parametrize("state", ["broken", "fouled"])
def test_go_park_still_retracts_a_broken_or_fouled_tip(state):
    """A failed attempt leaves the tip in one of these *and still down in the
    slice*, which is exactly the tip this action exists to get out."""
    ctx, pip = _parkCtx(state=state)

    go_park(ctx)

    assert len(pip.pipetteDevice.park_calls) == 1


def test_go_park_makes_no_move_for_a_tip_that_is_already_clear():
    """What lets the protocol and the orchestrator's safety net both call this
    without the second one costing a second move -- including the state change,
    which would otherwise end a recording for a tip that was never in the way."""
    ctx, pip = _parkCtx(state="whole cell")
    pip.pipetteDevice.parked = True

    go_park(ctx)

    assert pip.pipetteDevice.park_calls == []
    assert pip.set_state_calls == []


def test_go_park_sends_the_tip_home_when_there_is_nothing_left_to_stay_clear_of():
    """The end of a run: no cells queued and no survey to come. A tip left
    hovering over the slice has nothing to be ready for."""
    ctx, pip = _parkCtx(circle=None)
    pip.pipetteDevice.global_position = (1.0, 2.0, 3.0)
    pip.pipetteDevice.home_position = (0.0, 0.0, 0.0)

    go_park(ctx)

    assert pip.pipetteDevice.move_calls == [("home", "fast")]
    assert pip.pipetteDevice.park_calls == []


def test_go_park_does_not_re_home_a_tip_that_is_already_home():
    ctx, pip = _parkCtx(circle=None)
    pip.pipetteDevice.home_position = (0.0, 0.0, 0.0)
    pip.pipetteDevice.global_position = (0.0, 0.0, 10e-6)

    go_park(ctx)

    assert pip.pipetteDevice.move_calls == []
    assert pip.set_state_calls == []


def test_go_park_homes_anyway_when_the_manipulator_has_no_home_position():
    """A rig that cannot answer 'are you home' gets the move attempted and the
    real failure reported from there, rather than the park being refused over a
    question that was only ever a shortcut."""
    ctx, pip = _parkCtx(circle=None)
    pip.pipetteDevice.home_position = None

    go_park(ctx)

    assert pip.pipetteDevice.move_calls == [("home", "fast")]


def test_go_park_defaults_to_the_contexts_answer_of_none():
    """A context built without the orchestrator's closure -- headless, or a test
    -- has no queue to answer from, so the tip goes home rather than parking
    against a circle nobody supplied."""
    pip = FakePipette()
    ctx = ExecutionContext(pipette=pip)

    go_park(ctx)

    assert pip.pipetteDevice.move_calls == [("home", "fast")]


def test_go_park_reports_a_failed_state_change_as_an_orchestration_error():
    ctx, pip = _parkCtx(state="cell detect")
    pip.set_state_error = RuntimeError("clamp is gone")

    with pytest.raises(OrchestrationError) as exc:
        go_park(ctx)

    assert "bath" in str(exc.value)
    assert pip.pipetteDevice.park_calls == []
