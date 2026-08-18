"""Tests for the plain-function device actions (go_*, focus_*, new_pipette, find_tip,
find_surface, cellfie, run_task): fakes prove the right device calls happen in order."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, OrchestrationError, TrackingLost
from acq4.experiment.actions.device import (
    go_home,
    go_search,
    go_approach,
    go_target,
    go_above_target,
    focus_tip,
    focus_target,
    new_pipette,
    find_tip,
    find_surface,
    cellfie,
    run_task,
    load_preset,
)
from acq4.experiment.actions import device as device_mod
from acq4.util import Qt

# cellfie reaches acq4_automation twice at call time: for CellTrackingLost, and for
# DEFORMATION_TOLERANCE by way of AutomationDebug.feature_tracking. That package is
# internal and is not a declared dependency, so the tests that actually call cellfie
# only run where it is installed. Everything else in this module runs everywhere.
_CELLFIE_SKIP_REASON = "cellfie needs acq4_automation, an internal package"


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
    """Stands in for the acq4_automation tracker cellfie initializes: exposes
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
        if self.tracker_error is not None:
            raise self.tracker_error
        if self.tracker_stack is not None:
            self._tracker = _FakeTracker(self.tracker_stack)


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

    find_tip(ctx, speed="slow")

    assert pip.order == [
        ("move", "aboveTarget", "slow"),
        ("offset",),
        ("find_tip",),
    ]
    assert names == ["Find Pipette Tip"]


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


def _cellfie_context(monkeypatch, tmp_path, tissue_moved_hook=None):
    """An ExecutionContext wired for cellfie with the z-stack save stubbed out.

    cellfie's imaging is real-hardware work; only its tracker-initialization
    tail is under test here. FakePipette, FakeManager, and FakeCell already
    cover everything cellfie touches, so this only wires them together.
    """
    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    return ExecutionContext(
        cell=FakeCell(),
        pipette=FakePipette(),
        manager=FakeManager(),
        tissue_moved_hook=tissue_moved_hook,
    )


def test_cellfie_focuses_saves_zstack_and_initializes_tracker(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
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
    assert ctx.cell.tracker_calls == [(pip.imager, True)]
    # Whichever call site initializes a cell's tracker fixes its deformation tolerance
    # for that cell's lifetime, so this one has to forward it too.
    # Read from the constant's own module rather than through device.py: cellfie
    # imports it inside the function body, so it is not an attribute of that module.
    from acq4.modules.AutomationDebug.feature_tracking import DEFORMATION_TOLERANCE

    assert ctx.cell.tracker_kwargs == [
        {"deformation_tolerance": DEFORMATION_TOLERANCE, "segmenter": None}
    ]
    assert names == ["Cellfie"]


def test_cellfie_tracks_with_the_configured_segmenter(ctx, pip, monkeypatch):
    """Tracking has to segment with the same checkpoint detection uses; on stock
    cpsam it finds no cells in a tracking crop at all."""
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    pip.pipetteDevice.target_position = (0.0, 0.0, 100e-6)
    monkeypatch.setattr(
        device_mod, "run_image_sequence", lambda *a, **k: _Waitable()
    )
    monkeypatch.setattr(device_mod, "segmenter_path", lambda: "/models/tuned")

    cellfie(ctx, height=30e-6, step=1e-6)

    assert ctx.cell.tracker_kwargs[0]["segmenter"] == "/models/tuned"


def test_cellfie_default_height_and_step(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
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


def test_cellfie_routes_a_lost_cell_to_the_tissue_moved_hook(monkeypatch, tmp_path):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    seen = []

    def hook(ctx, reason):
        seen.append(reason)
        ctx.next_cell()

    ctx = _cellfie_context(monkeypatch, tmp_path, tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features matched")

    with pytest.raises(AdvanceToNextCell):
        cellfie(ctx)
    assert seen == ["no features matched"]


def test_cellfie_lets_an_unrelated_valueerror_propagate(monkeypatch, tmp_path):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    # Only the named class is tissue motion. A bare ValueError out of the
    # tracker stack is a bug, and classifying it as motion would trigger a
    # destructive rescan whose prompt defaults to "Rescan".
    called = []
    ctx = _cellfie_context(
        monkeypatch, tmp_path, tissue_moved_hook=lambda c, r: called.append(r)
    )
    ctx.cell.tracker_error = ValueError("something else entirely")

    with pytest.raises(ValueError, match="something else entirely"):
        cellfie(ctx)
    assert called == []


def test_cellfie_with_no_hook_raises_trackinglost(monkeypatch, tmp_path):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    ctx = _cellfie_context(monkeypatch, tmp_path)
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features")

    with pytest.raises(TrackingLost):
        cellfie(ctx)


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


def test_cellfie_retains_the_trackers_stack_as_an_image_stack_payload(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    import numpy as np

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "image_stack"
    # Rows/cols swapped so it displays in the same orientation as the Camera
    # module, matching AutomationDebug's own cell stack view.
    assert payload["stack"].shape == (5, 3, 4)
    assert payload["center_index"] == 2
    assert payload["title"] == "Cellfie"


def test_cellfie_center_index_is_none_for_a_single_frame_stack(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    import numpy as np

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = np.zeros((1, 4, 3))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert details[0][1]["center_index"] is None


def test_cellfie_sets_no_payload_when_the_tracker_exposes_no_stack(ctx, pip, monkeypatch):
    # A cell whose tracker did not expose a stack must not make cellfie raise
    # out of the orchestrator's worker thread over a display concern.
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = None
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert details == []


def test_cellfie_sets_no_payload_when_the_cell_is_lost(monkeypatch, tmp_path):
    # tissue_moved never returns, so there is nothing to retain -- the accepted
    # gap in the spec's §8.
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    def hook(c, reason):
        raise AdvanceToNextCell(reason)

    ctx = _cellfie_context(monkeypatch, tmp_path, tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("gone")
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    with pytest.raises(AdvanceToNextCell):
        cellfie(ctx)

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
    assert payload["sweep_count"] == 2
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

    assert details[0][1]["sweep_count"] == 0
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

    assert details[0][1]["sweep_count"] == 1


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
    assert details[0][1]["sweep_count"] == 2
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
