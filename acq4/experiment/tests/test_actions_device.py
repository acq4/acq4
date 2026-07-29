"""Tests for the plain-function device actions (go_*, focus_*, new_pipette, find_tip,
find_surface, cellfie, run_task): fakes prove the right device calls happen in order."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import OrchestrationError
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
)
from acq4.experiment.actions import device as device_mod


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

    def findSurfaceDepth(self, imager):
        self.calls.append(imager)
        if self.error is not None:
            raise self.error
        return self.depth


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


class FakeTaskRunnerModule:
    def __init__(self, docks, period=1.0, totalParams=5):
        self.docks = docks
        self.sequenceInfo = {"period": period, "totalParams": totalParams}
        self.run_calls = []

    def runSequence(self, store=True):
        self.run_calls.append(store)
        return _Waitable()


class FakeCell:
    def __init__(self):
        self.tracker_calls = []

    def initializeTracker(self, imager, use_cellpose=False):
        self.tracker_calls.append((imager, use_cellpose))


@pytest.fixture
def pip():
    return FakePipette()


@pytest.fixture
def ctx(pip):
    return ExecutionContext(pipette=pip, manager=FakeManager(), cell=FakeCell())


def _entry_names(ctx):
    names = []
    ctx.on_log_action = lambda entry: names.append(entry.name)
    return names


# -- named moves --------------------------------------------------------


@pytest.mark.parametrize(
    "fn, name, position",
    [
        (go_home, "GoHome", "home"),
        (go_search, "GoSearch", "search"),
        (go_approach, "GoApproach", "approach"),
        (go_target, "GoTarget", "target"),
        (go_above_target, "GoAboveTarget", "aboveTarget"),
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
    assert names == ["FocusTip"]


def test_focus_target_dispatches_to_focus_on_target(ctx, pip):
    names = _entry_names(ctx)

    focus_target(ctx, speed="slow")

    assert pip.focus_calls == [("target", "slow")]
    assert names == ["FocusTarget"]


# -- new_pipette ------------------------------------------------------------


def test_new_pipette_calls_new_pipette_and_waits(ctx, pip):
    names = _entry_names(ctx)

    new_pipette(ctx)

    assert pip.new_pipette_calls == 1
    assert names == ["NewPipette"]


def test_new_pipette_wraps_failure_as_orchestration_error(ctx, pip):
    pip.new_pipette_error = RuntimeError("boom")

    with pytest.raises(OrchestrationError) as excinfo:
        new_pipette(ctx)

    assert "NewPipette" in str(excinfo.value)
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
    assert names == ["FindTip"]


def test_find_tip_wraps_failure_as_orchestration_error(ctx, pip):
    pip.pipetteDevice.find_tip_error = RuntimeError("no tip")

    with pytest.raises(OrchestrationError) as excinfo:
        find_tip(ctx)

    assert "FindTip" in str(excinfo.value)
    assert "no tip" in str(excinfo.value)


# -- find_surface -------------------------------------------------------


def test_find_surface_returns_depth(ctx, pip):
    names = _entry_names(ctx)
    pip.scope.depth = 123.4

    result = find_surface(ctx)

    assert result == 123.4
    assert pip.scope.calls == [pip.imager]
    assert names == ["FindSurface"]


def test_find_surface_wraps_value_error(ctx, pip):
    pip.scope.error = ValueError("no surface")

    with pytest.raises(OrchestrationError) as excinfo:
        find_surface(ctx)

    assert "FindSurface" in str(excinfo.value)
    assert "no surface" in str(excinfo.value)


# -- cellfie --------------------------------------------------------------


def test_cellfie_focuses_saves_zstack_and_initializes_tracker(ctx, pip, monkeypatch):
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
    assert names == ["Cellfie"]


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
    assert names == ["Task"]


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

    assert "Task" in str(excinfo.value)
    assert "Clamp1" in str(excinfo.value)
