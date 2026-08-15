"""Integration test: loading a protocol builds and binds a fresh Orchestrator
to the window's StatusPanel/CellPanel, and a seeded cell runs end-to-end."""
import importlib
import os
from types import SimpleNamespace

import numpy as np
import pyqtgraph as pg
import pytest
from coorx import Point

import acq4.util.DataManager as dm
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell
from acq4.experiment.search_region import EllipseRegion, RectRegion
from acq4.experiment.slice import Slice
from acq4.modules.Autopatch.progress_colors import (
    COLOR_SOURCES,
    ColorContext,
    healthBrushes,
    successBrushes,
)
from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException
from acq4_automation.feature_tracking.cell import Cell


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakePipetteSelector(Qt.QWidget):
    """Stands in for InterfaceCombo so the test never triggers its internal
    getManager() call."""

    def __init__(self, target=None):
        super().__init__()
        self._target = target

    def getSelectedObj(self):
        if self._target is None:
            return None
        return _FakePipette(self._target)


class _FakePipette:
    """Stands in for a PatchPipette: exposes .pipetteDevice.targetPosition()
    the way a real PatchPipette delegates target lookups to its manipulator,
    plus a direct targetPosition() convenience so tests can assert on the
    cached ctx.pipette's value without reaching into .pipetteDevice."""

    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)

    def targetPosition(self):
        return self.pipetteDevice.targetPosition()


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakeCameraSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


class _FakeScope:
    """Stands in for a Microscope: records survey moves and reports a surface."""

    def __init__(self):
        self.moves = []

    def setGlobalPosition(self, pos, speed="fast", name=None):
        self.moves.append(tuple(pos))
        return _DoneFuture()

    def findSurfaceDepth(self, imager):
        return 0.0


class _DoneFuture:
    def wait(self, **kwargs):
        return None


class _FakeCamera:
    """Stands in for a Camera: the three calls a cell producer's install needs.

    getBoundary in "roi" mode gives the field a tile covers, globalCenterPosition
    in "roi" mode gives where to seed a region, and scopeDev is the stage the
    detector drives.

    Mode-sensitive like the real Camera.getBoundary/globalCenterPosition
    (acq4/devices/Camera/Camera.py): a cropped camera ROI sits off-center on
    the sensor, so "roi" and "sensor" must answer with different rectangles
    and different centers here too, or a caller that reaches for the wrong
    mode string would coincidentally get away with it against this fake. The
    ROI's field is also non-square and, by default, centered away from the
    origin, so a region built from the wrong axis or from (0, 0) instead of
    the camera's actual center shows up as a wrong coordinate rather than
    passing by symmetry.
    """

    def __init__(self, roi_fov=(12e-6, 8e-6), roi_center=(5e-6, -3e-6, 0.0)):
        self._roi_fov = roi_fov
        self._roi_center = roi_center
        # Larger than the ROI and centered on the origin -- a different
        # rectangle, not the ROI under another name.
        self._sensor_fov = (roi_fov[0] * 4, roi_fov[1] * 4)
        self._sensor_center = (0.0, 0.0, 0.0)
        self.scopeDev = _FakeScope()

    def name(self):
        return "FakeCamera"

    def getBoundary(self, globalCoords=True, mode="sensor"):
        if mode == "roi":
            w, h = self._roi_fov
            cx, cy, _ = self._roi_center
        elif mode == "sensor":
            w, h = self._sensor_fov
            cx, cy, _ = self._sensor_center
        else:
            raise ValueError(f"mode must be 'sensor' or 'roi', got {mode!r}")
        if not globalCoords:
            # Local coordinates are pixel-space, a completely different scale
            # than the metre-scale global bounds below -- a caller that reads
            # this without globalCoords=True gets an obviously wrong field of
            # view rather than one that happens to still look like metres.
            return 0.0, 0.0, w * 1e6, h * 1e6
        return cx - w / 2, cy - h / 2, w, h

    def globalCenterPosition(self, mode="sensor"):
        if mode == "roi":
            return self._roi_center
        elif mode == "sensor":
            return self._sensor_center
        raise ValueError(f"mode must be 'sensor' or 'roi', got {mode!r}")

    def getPixelSize(self):
        return (0.32e-6, 0.32e-6)


class _FakeCameraWithDevice(Qt.QWidget):
    """A camera selector that actually returns a camera, unlike _FakeCameraSelector."""

    def __init__(self, camera=None):
        super().__init__()
        self.camera = camera if camera is not None else _FakeCamera()

    def getSelectedObj(self):
        return self.camera


class _FakePinnedFrameSource(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl: the pinned-frame list and
    the signal Area 1 mirrors it through.

    clearPinnedFrames() genuinely empties the list and emits, because the real
    one does (via removePinnedFrame) -- ReferenceImagery.beginSlice() calls it
    when the operator agrees to clear a previous slice's frames, and a fake
    that only recorded the call rather than emptying the list would hide a
    missing recompute in the code under test.
    """

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self):
        super().__init__()
        self.pinnedFrames = []

    def clearPinnedFrames(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()


# The one folder type newSlice() asks create_data_dir for. A real Manager's
# config carries many more, but this window only ever creates a "Slice".
_FOLDER_TYPES = {"Slice": {"name": "Slice_%Y%m%d_%H%M%S", "experimentalUnit": False}}


class _FakeManager(Qt.QObject):
    """Stands in for Manager: backed by a real DirHandle (on tmp_path) so
    create_data_dir's mkdir/setInfo calls land on an actual directory, the way
    they would through the real Manager AutopatchWindow otherwise gets from
    its module.

    Offers a Camera module by default, because the Autopatch module opens one
    at startup and everything in Area 1 is written to assume it. A fake that
    reported none would stand for a state production rules out.

    A QObject carrying sigModulesChanged, because the real Manager is one.
    Nothing in Autopatch listens to that signal, so the fake's implementation
    is inert; it exists to match the interface of the thing it stands in for.
    """

    sigModulesChanged = Qt.Signal()

    def __init__(self, root_dir):
        super().__init__()
        self._current_dir = root_dir
        self.drawn = []
        self.pinnedFrameSource = _FakePinnedFrameSource()
        self.cameraWindow = SimpleNamespace(
            getInterfaceForDevice=lambda name: SimpleNamespace(
                imagingCtrl=self.pinnedFrameSource
            ),
            addItem=lambda item, **kwds: self.drawn.append(item),
            removeItem=self.drawn.remove,
        )

    def listModules(self):
        return ["Camera", "Data Manager"]

    def getModule(self, name):
        if name != "Camera":
            raise KeyError(name)
        return SimpleNamespace(window=lambda: self.cameraWindow)

    def getCurrentDir(self):
        return self._current_dir

    def setCurrentDir(self, d):
        self._current_dir = d

    def folderTypesConfig(self):
        return _FOLDER_TYPES


def _makeWindow(tmp_path, cameraSelector=None):
    """An AutopatchWindow with a loaded no-op protocol and a camera-backed
    selector, for tests that don't care about protocol content but do need a
    working camera to seed a slice or region.

    Also wires up a manager backed by a real (temporary) managed directory, so
    newSlice()'s create_data_dir call has somewhere real to write -- kept in a
    subdirectory of tmp_path separate from the protocol files written directly
    into tmp_path above."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    if cameraSelector is None:
        cameraSelector = _FakeCameraWithDevice()
    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    storageRoot = dm.getDirHandle(str(tmp_path / "storage"), create=True)
    win = AutopatchWindow(
        module=SimpleNamespace(manager=_FakeManager(storageRoot)),
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=cameraSelector,
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")
    return win


def _makeCell():
    """A Cell at an arbitrary global position, standing in for one a real
    detector would have found -- only its identity matters to these tests."""
    return Cell(Point([1e-3, 2e-3, -30e-6], "global"))


def _makeCellAt(x, y, z=-30e-6):
    """A Cell at a chosen global position, for tests that care where it is.

    _makeCell()'s fixed position is enough when only identity matters; density
    and navigation need cells that differ in both x and y.
    """
    return Cell(Point([x, y, z], "global"))


_NOOP_PROTOCOL = '''"""Integration test fixture: resolves immediately without touching ctx."""


def run(ctx, **kwargs):
    return None
'''


def _write_protocol(path, name, body):
    with open(os.path.join(path, name), "w") as fh:
        fh.write(body)


@pytest.fixture
def win(qapp, tmp_path):
    w = _makeWindow(tmp_path)
    yield w
    # Without this, every one of the many tests parametrized on this fixture
    # leaves behind a fully-built AutopatchWindow (Orchestrator, panels,
    # ParameterTree) that only Python's cyclic GC can reclaim, since teardown()
    # is what breaks the Orchestrator/Cell/window reference cycle -- see its
    # docstring. Left to the collector, that reclaim happens at an arbitrary
    # later point (possibly in an unrelated test module), where it can delete a
    # live QObject while a Qt event is still queued for it.
    w.teardown()


def test_loading_a_protocol_builds_and_binds_an_orchestrator(qapp, tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    assert win.orchestrator is not None
    assert win.orchestrator.protocolFile is win.protocolPanel.protocolFile
    # StatusPanel/CellPanel are bound: clicking Start reaches the real orchestrator.
    win.statusPanel.startBtn.click()
    win.orchestrator.wait(timeout=2)


def test_initial_populate_already_binds_an_orchestrator(qapp, tmp_path):
    """An operator who opens the window and immediately presses Start must
    get a run -- the protocol selected by the panel's own first scan (before
    the window ever wires up sigProtocolLoaded) must still end up bound."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraSelector(),
    )

    assert win.protocolPanel.fileCombo.currentText() == "demo"
    assert win.orchestrator is not None
    assert win.orchestrator.protocolFile is win.protocolPanel.protocolFile
    win.statusPanel.startBtn.click()
    win.orchestrator.wait(timeout=2)


_NOOP_LOGGING_PROTOCOL = '''"""Integration test fixture: logs via ctx.log and opens a single log_action, so
a seeded cell can run through to completion while exercising both the log
view and the Area 5 timeline."""


def run(ctx, **kwargs):
    ctx.log(f"ran on {ctx.cell!r}")
    with ctx.log_action("Noop") as action_entry:
        action_entry.set_status("doing nothing in particular")
'''


def _write_noop_protocol(path, name):
    _write_protocol(path, name, _NOOP_LOGGING_PROTOCOL)


def test_full_flow_seeds_a_cell_starts_and_updates_status_timeline_log(qapp, qtbot, tmp_path):
    """Headless end-to-end check: load protocol -> seed a cell via "Add from
    target" -> Start -> status/timeline/log all reflect the run.

    The orchestrator runs its queue on a worker thread and marshals signals back
    to the GUI thread via queued connections, so this test uses qtbot.waitUntil
    (which pumps the Qt event loop) rather than a bare Orchestrator.wait().
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_noop_protocol(tmp_path, "demo.py")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    win.cellPanel.addFromTargetBtn.click()
    assert win.cellPanel.cellList.count() == 1
    assert "queued" in win.cellPanel.cellList.item(0).text()

    win.statusPanel.startBtn.click()
    qtbot.waitUntil(lambda: "done" in win.cellPanel.cellList.item(0).text(), timeout=2000)

    assert "waiting" in win.statusPanel.statusLabel.text().lower()

    win.cellPanel.cellList.setCurrentRow(0)
    timelineLines = [
        win.cellPanel.timelineList.item(i).text()
        for i in range(win.cellPanel.timelineList.count())
    ]
    # A timeline row's label comes from the ctx.log_action() name ("Noop" here,
    # opened once by the protocol above) rather than a graph node id; the
    # elapsed-time suffix is non-deterministic, so check the fixed prefix only.
    assert len(timelineLines) == 1
    assert timelineLines[0].startswith("Noop — ✓ done")

    assert "ran on" in win.cellPanel.logView.toPlainText()


class _CountingPipetteSelector(Qt.QWidget):
    """Like _FakePipetteSelector, but counts getSelectedObj() calls and allows
    mutating the "selection" mid-test, so a test can prove the context factory
    reads a cached pipette rather than re-consulting the selector widget."""

    def __init__(self, target):
        super().__init__()
        self._target = target
        self.callCount = 0

    def getSelectedObj(self):
        self.callCount += 1
        return _FakePipette(self._target)

    def setTarget(self, target) -> None:
        self._target = target


_PIPETTE_CAPTURE_PROTOCOL = '''"""Integration test fixture: reads ctx.pipette at two separate points in the
protocol body and stashes both onto ctx.cell. The first write lets the test
wait for the run to reach that point; the second lets it inspect the pipette
snapshot ctx took at Start, from a point later in the same run."""


def run(ctx, **kwargs):
    ctx.cell._firstPipette = ctx.pipette
    ctx.cell._secondPipette = ctx.pipette
'''


def _write_pipette_capture_protocol(path, name):
    _write_protocol(path, name, _PIPETTE_CAPTURE_PROTOCOL)


def test_pipette_is_snapshotted_at_start_not_read_from_selector_mid_run(qapp, qtbot, tmp_path):
    """The context factory must not call the pipette selector widget from the
    orchestrator's worker thread during a run (a race on currentIndex()/
    interfaceMap). It should read a plain object cached at Start (GUI thread):
    the resolved pipette's target matches the selector's state at Start
    (not the mid-run mutation below), and the selector is consulted exactly
    once for the whole run."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_pipette_capture_protocol(tmp_path, "demo.py")

    selector = _CountingPipetteSelector(target=(1e-3, 2e-3, 3e-3))
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=selector,
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    win.cellPanel.addFromTargetBtn.click()
    assert win.cellPanel.cellList.count() == 1
    seededCell = list(win.cellPanel._cells.values())[0]

    callsBeforeStart = selector.callCount
    win.statusPanel.startBtn.click()
    # Simulate the operator changing the pipette selection immediately after
    # Start -- the in-flight run must not notice.
    selector.setTarget((9e-3, 9e-3, 9e-3))

    qtbot.waitUntil(lambda: hasattr(seededCell, "_secondPipette"), timeout=2000)

    assert seededCell._firstPipette.targetPosition() == pytest.approx((1e-3, 2e-3, 3e-3))
    # Resolved exactly once (at Start) -- not once per protocol step, and not
    # affected by the mid-run mutation above.
    assert selector.callCount == callsBeforeStart + 1


_SLOW_PROTOCOL = '''"""Integration test fixture: loops until stopped, so a test can observe an
in-flight run before it finishes."""
from acq4.util.task import check_stop, sleep


def run(ctx, **kwargs):
    while True:
        check_stop()
        sleep(0.01)
'''


def _write_slow_protocol(path, name):
    _write_protocol(path, name, _SLOW_PROTOCOL)


def test_loading_a_second_protocol_stops_and_releases_the_previous_orchestrator(
    qapp, qtbot, tmp_path
):
    """Loading a second protocol must not abandon a still-live, still-running
    Orchestrator: it must be stopped and unparented before the new one is
    built, so it stops writing into the window's panels and is free to be
    garbage collected.

    Drives this through selecting the protocol in the combo directly rather
    than a button click, deliberately: Area 4's picker is disabled while a
    run is in flight (see test_area4_controls_disabled_while_running_and_
    reenabled_when_stopped, below), so re-selecting is not reachable mid-run
    either. This test exists to cover the sigProtocolLoaded path itself, not
    to claim the operator can trigger it mid-run."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_slow_protocol(tmp_path, "slow.py")
    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("slow")
    firstOrchestrator = win.orchestrator
    win.cellPanel.addFromTargetBtn.click()  # a queued cell so the run loop body actually runs

    win.statusPanel.startBtn.click()
    task = firstOrchestrator._task
    qtbot.wait(50)  # give the worker thread a moment to actually be running
    assert not task.is_done

    win.protocolPanel.fileCombo.setCurrentText("demo")

    assert win.orchestrator is not None
    assert win.orchestrator is not firstOrchestrator
    assert task.is_done
    assert task.is_stopped
    # No longer a Qt child of the window -- nothing left to keep it alive.
    assert firstOrchestrator.parent() is None


def test_switching_to_a_different_protocol_carries_over_still_pending_seeded_cells(
    qapp, tmp_path
):
    """A cell seeded through Area 5 while an orchestrator is bound is
    enqueued straight into that orchestrator's own queue by
    CellPanel._enqueueAndAdd(), and recorded in _awaitingEnqueue nowhere.
    _onProtocolLoaded releases the whole outgoing Orchestrator -- its queue
    included -- when the operator switches to a different protocol, so
    without CellPanel.unbindOrchestrator() salvaging that queue first, the
    seeded cell's row would survive in Area 5 while the freshly bound
    orchestrator's queue held nothing for it, and pressing Start would patch
    nothing."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "first.py", _NOOP_PROTOCOL)
    _write_protocol(tmp_path, "second.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraWithDevice(),
    )
    win.protocolPanel.fileCombo.setCurrentText("first")
    firstOrchestrator = win.orchestrator

    win.cellPanel._onScatterFakeCellsClicked()
    seededCells = list(win.cellPanel._cells.values())
    assert seededCells
    assert firstOrchestrator.pendingCells() == seededCells

    win.protocolPanel.fileCombo.setCurrentText("second")

    assert win.orchestrator is not None
    assert win.orchestrator is not firstOrchestrator
    assert win.orchestrator.pendingCells() == seededCells
    assert win.cellPanel.cellList.count() == len(seededCells)


def test_a_finished_cell_seeded_while_bound_is_not_reflushed_on_protocol_switch(
    qapp, qtbot, tmp_path
):
    """Complements the test above from the other direction: a cell seeded
    while an orchestrator is bound is also enqueued straight into that
    orchestrator's queue, but once a run actually pops and finishes it,
    Orchestrator.pendingCells() no longer reports it. Switching to a
    different protocol afterward must not hand that finished cell to the
    freshly bound orchestrator for a second run -- the same pipette-safety
    invariant the panel-level tests pin against an announced-only cell,
    checked here against one this panel seeded itself."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_noop_protocol(tmp_path, "first.py")
    _write_protocol(tmp_path, "second.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("first")
    firstOrchestrator = win.orchestrator

    win.cellPanel.addFromTargetBtn.click()
    win.statusPanel.startBtn.click()
    qtbot.waitUntil(
        lambda: "done" in win.cellPanel.cellList.item(0).text(), timeout=2000
    )
    assert firstOrchestrator.pendingCells() == []

    win.protocolPanel.fileCombo.setCurrentText("second")

    assert win.orchestrator is not None
    assert win.orchestrator is not firstOrchestrator
    assert win.orchestrator.pendingCells() == []


def test_area4_controls_disabled_while_running_and_reenabled_when_stopped(
    qapp, qtbot, tmp_path
):
    """Area 4 (the protocol picker and Reload) must not be usable while a
    run is in flight -- selecting a different protocol mid-run would
    otherwise leave two worker threads eligible to drive the same pipette."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_slow_protocol(tmp_path, "slow.py")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("slow")
    win.cellPanel.addFromTargetBtn.click()  # a queued cell so the run loop body actually runs
    assert win.protocolPanel.fileCombo.isEnabled()
    assert win.protocolPanel.reloadBtn.isEnabled()

    win.statusPanel.startBtn.click()
    qtbot.wait(50)

    assert not win.protocolPanel.fileCombo.isEnabled()
    assert not win.protocolPanel.reloadBtn.isEnabled()

    win.orchestrator.stop()
    qtbot.waitUntil(lambda: win.protocolPanel.fileCombo.isEnabled(), timeout=2000)
    assert win.protocolPanel.reloadBtn.isEnabled()


def test_a_fresh_window_has_no_slice(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    # A slice is a commitment to a piece of tissue under the objective; the
    # window must not invent one before the operator says so.
    assert win.slice is None


def test_new_slice_creates_a_slice_using_the_cameras_field_of_view(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    assert win.slice is not None
    assert win.slice.tileGrid() == [], "a new slice has no regions to survey yet"

    # The slice's field of view must be the camera's "roi" boundary, in the
    # camera's own axis order -- not swapped, which would give the tile grid
    # the wrong stride in each direction (the fake's roi_fov is deliberately
    # non-square so a swap cannot pass by coincidence).
    camera = win.cameraSelector.getSelectedObj()
    _, _, fov_w, fov_h = camera.getBoundary(globalCoords=True, mode="roi")
    assert win.slice._fov == pytest.approx((abs(fov_w), abs(fov_h)))


def test_new_slice_without_a_camera_reports_rather_than_raising(qapp, tmp_path):
    # _FakeCameraSelector returns None, the camera-less case.
    win = _makeWindow(tmp_path, cameraSelector=_FakeCameraSelector())
    win.newSlice()
    assert win.slice is None
    assert win.searchPanel.errorLabel.text() != ""


def test_the_no_camera_message_survives_a_constraint_edit(qapp, tmp_path):
    """The window reports "no camera" through SearchPanel.setError(), not by
    writing into errorLabel behind the panel's back: a valid spin box edit calls
    SearchPanel.constraints(), which rewrites that same label, and would
    otherwise erase the operator's only feedback while no slice exists."""
    win = _makeWindow(tmp_path, cameraSelector=_FakeCameraSelector())
    win.newSlice()
    message = win.searchPanel.errorLabel.text()
    assert message != ""

    win.searchPanel.minHealthSpin.setValue(0.75)

    assert win.searchPanel.errorLabel.text() == message


def test_a_started_slice_retracts_the_no_camera_message(qapp, tmp_path):
    # There is a camera now, so the message must not linger.
    selector = _FakeCameraWithDevice()
    win = _makeWindow(tmp_path, cameraSelector=_FakeCameraSelector())
    win.newSlice()
    assert win.searchPanel.errorLabel.text() != ""

    win.cameraSelector = selector
    win.newSlice()

    assert win.slice is not None
    assert win.searchPanel.errorLabel.text() == ""


def test_new_slice_reports_rather_than_raising_when_the_camera_module_is_closed(
    qapp, tmp_path
):
    # The owner's second precondition, alongside "clear() swallows,
    # _redraw() propagates": Autopatch.__init__ opens the Camera module at
    # startup, so a manager present with it missing or windowless means it
    # closed underneath a running session, and _cameraModuleWindow raises
    # rather than answering None (see its docstring). _canStartSlice()'s
    # try/except around that call is what keeps this raise from escaping into
    # New slice's click handler -- reporting it through SearchPanel exactly
    # as it already does for "no camera selected" -- and deleting that
    # try/except is one of the two mutations the reviewer found the whole
    # suite stayed green under.
    win = _makeWindow(tmp_path)

    def boom():
        raise HelpfulException("The Camera module is not open.")

    win._cameraWindow = boom

    win.newSlice()

    assert win.slice is None
    assert "Camera module" in win.searchPanel.errorLabel.text()


def test_new_slice_with_invalid_constraints_creates_nothing_and_keeps_the_old_slice(
    qapp, tmp_path
):
    # Spin box values that do not describe a valid search must not install a
    # half-built slice over a good one, nor discard what the good one holds.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win.cellPanel._onScatterFakeCellsClicked()
    first = win.slice
    seededCells = win.cellPanel.cellList.count()
    assert seededCells > 0

    # Equal near and far depths span no thickness, so SearchConstraints rejects
    # them and SearchPanel.constraints() reports None.
    win.searchPanel.farDepthSpin.setValue(win.searchPanel.nearDepthSpin.value())
    win.newSlice()

    assert win.slice is first
    assert len(win.slice.regions) == 1
    assert win.cellPanel.cellList.count() == seededCells
    assert win.searchPanel.errorLabel.text() != ""


def test_add_region_here_seeds_a_multi_tile_region(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    assert len(win.slice.regions) == 1
    assert len(win.slice.tileGrid()) > 1

    # The region itself must be 3x3 fields of view, centered on the camera's
    # "roi" center -- not the sensor's, not the origin, and not anchored at a
    # corner of the camera's center instead of straddling it. Computed
    # independently of _cameraFov()/addRegionHere() (straight off the fake's
    # "roi" boundary/center) so a bug in either of those is caught rather than
    # echoed back at itself.
    camera = win.cameraSelector.getSelectedObj()
    _, _, fov_w, fov_h = camera.getBoundary(globalCoords=True, mode="roi")
    cx, cy, _ = camera.globalCenterPosition("roi")
    region = win.slice.regions[0]
    assert isinstance(region, RectRegion)
    x0, y0, x1, y1 = region.bounds()
    assert x0 == pytest.approx(cx - 3 * fov_w / 2)
    assert y0 == pytest.approx(cy - 3 * fov_h / 2)
    assert x1 == pytest.approx(cx + 3 * fov_w / 2)
    assert y1 == pytest.approx(cy + 3 * fov_h / 2)


def test_add_region_here_without_a_slice_starts_one(qapp, tmp_path):
    # Seeding a region is a reasonable first action: a slice comes into
    # existence to hold it rather than the region being dropped.
    win = _makeWindow(tmp_path)
    assert win.slice is None

    win.addRegionHere()

    assert win.slice is not None
    assert len(win.slice.regions) == 1
    assert len(win.slice.tileGrid()) > 1


def test_add_region_here_builds_the_shape_area_1_selects(qapp, tmp_path):
    # The button has to read the selector rather than always building a
    # rectangle.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.regionPanel.shapeCombo.setCurrentIndex(
        win.regionPanel.shapeCombo.findData("ellipse")
    )

    win.addRegionHere()

    region = win.slice.regions[0]
    assert isinstance(region, EllipseRegion)
    # Inscribed in the same 3x3-field box a rectangle would have used, centered
    # on the camera's "roi" center -- computed off the fake camera directly so a
    # bug in _cameraFov() is caught rather than echoed back.
    camera = win.cameraSelector.getSelectedObj()
    _, _, fov_w, fov_h = camera.getBoundary(globalCoords=True, mode="roi")
    cx, cy, _ = camera.globalCenterPosition("roi")
    assert region.bounds() == pytest.approx(
        (
            cx - 3 * fov_w / 2,
            cy - 3 * fov_h / 2,
            cx + 3 * fov_w / 2,
            cy + 3 * fov_h / 2,
        )
    )
    # And it is actually surveyable, not merely recorded.
    assert len(win.slice.tileGrid()) > 1


def test_add_region_here_without_a_slice_keeps_hand_seeded_cells(qapp, tmp_path):
    """Creating the slice that will hold the region must not go through
    newSlice(), which is the discard-everything path: the add-region button
    offers only to add a region, and an operator who seeded cells by hand first
    must still have them -- both the rows and the orchestrator's queue.
    """
    win = _makeWindow(tmp_path)
    assert win.slice is None
    win.cellPanel._onScatterFakeCellsClicked()
    seeded = win.cellPanel.cellList.count()
    assert seeded > 0
    queued = list(win.orchestrator._queue)
    assert len(queued) == seeded

    win.addRegionHere()

    assert win.slice is not None
    assert len(win.slice.regions) == 1
    assert win.cellPanel.cellList.count() == seeded
    assert list(win.orchestrator._queue) == queued


def test_new_slice_replaces_the_slice_and_its_coverage(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    first = win.slice
    first.markCovered(first.nextTile())

    win.newSlice()

    assert win.slice is not first
    assert win.slice.regions == []
    assert win.slice.coveredTiles == []


def test_new_slice_clears_the_cell_list_and_the_orchestrators_queue(qapp, tmp_path):
    # A Cell is a coordinate in tissue. Swapped tissue makes every one of those
    # coordinates a place not to drive a pipette, so both the panel's list and
    # the orchestrator's separate deque have to let go.
    win = _makeWindow(tmp_path)
    win.cellPanel._onScatterFakeCellsClicked()
    assert win.cellPanel.cellList.count() > 0

    ran = []
    win.orchestrator.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)

    win.newSlice()

    assert win.cellPanel.cellList.count() == 0
    win.orchestrator.run_sync()
    assert ran == [], "a cell survived New slice and was patched anyway"


def test_new_slice_clears_area_3s_error_band(qapp, tmp_path):
    """Area 3's band names a cell and a failure that happened on tissue New
    slice has just declared gone. clearCells() drops Area 5's own error store
    for exactly this reason (see test_new_slice_clears_the_cell_list_and_the_
    orchestrators_queue above); the band needs the same discard, or the two
    panels disagree about whether the halted run still means anything.
    """
    from acq4.experiment.exceptions import AbortExperiment

    _write_protocol(tmp_path, "boom.py", _RAISING_PROTOCOL)
    win = _makeWindow(tmp_path)
    try:
        win.protocolPanel.fileCombo.setCurrentText("boom")
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        with pytest.raises(AbortExperiment):
            win.orchestrator.run_sync()

        assert win.statusPanel.lastError() is not None
        assert win.statusPanel.instructionLabel.isVisibleTo(win.statusPanel)

        win.newSlice()

        assert win.statusPanel.lastError() is None
        # The band is not empty -- the default fake pins no frames, so
        # newSlice() leaves the imagery instruction showing -- but that text
        # is proof the error slot itself is empty, not merely that the whole
        # band is.
        assert win.statusPanel.instructionLabel.isVisibleTo(win.statusPanel)
        assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION
    finally:
        win.teardown()


def test_new_slice_leaves_the_in_flight_cell_unreusable(qapp, tmp_path):
    """newSlice() deliberately lets the cell already in flight run to
    completion, so its finish is announced after Area 5 has been cleared. That
    announcement must not resurrect the cell as a reusable one: the operator
    has declared the tissue it names gone, and "Check all completed" would
    otherwise tick it without them singling it out at all.
    """
    win = _makeWindow(tmp_path)
    try:
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)
        # The wipe lands from inside the cell's own protocol, which is exactly
        # where a New slice click lands in practice: the cell is in the
        # orchestrator's hand, and it goes on to finish on the old tissue
        # afterward, as newSlice()'s docstring says it is allowed to. Driven
        # inline (run_sync) rather than by emitting the signals by hand, so the
        # real orchestrator really is holding the cell across the wipe.
        def run(ctx, **kwargs):
            assert win.cellPanel.isAttempted(ctx.cell) is True
            win.newSlice()

        win.orchestrator.protocolFile.run = run

        win.orchestrator.run_sync()

        assert win.cellPanel.cellList.count() == 0
        assert win.cellPanel.disposition(cell) is None
        assert win.cellPanel.isAttempted(cell) is False
        assert not win.cellPanel.checkAllCompletedBtn.isEnabled()
    finally:
        win.teardown()


def test_new_slice_after_a_cells_finish_was_delivered_leaves_it_unreusable(
    qapp, tmp_path
):
    """The other ordering abandonCellInHand() covers, and the one it covers by
    doing nothing: the cell's terminal disposition has already been delivered
    when the wipe lands, so nothing is in hand to mark -- and the row that
    disposition built is removed by clearCells() because it existed before the
    wipe. Qt dispatches a posted signal ahead of a click posted after it, so this
    is the ordering a New slice pressed once a cell has finished actually takes.

    Its counterpart -- an emit whose queued delivery is still pending when the
    wipe runs -- is not covered; see abandonCellInHand's docstring.
    """
    win = _makeWindow(tmp_path)
    try:
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        # Run to completion first, so the disposition is recorded and its row
        # exists before the wipe rather than arriving after it.
        win.orchestrator.run_sync()
        assert win.cellPanel.disposition(cell) == "done"
        assert win.cellPanel.checkAllCompletedBtn.isEnabled()

        win.newSlice()

        assert win.cellPanel.cellList.count() == 0
        assert win.cellPanel.disposition(cell) is None
        assert win.cellPanel.isAttempted(cell) is False
        assert not win.cellPanel.checkAllCompletedBtn.isEnabled()
    finally:
        win.teardown()


def test_two_new_slices_in_a_row_still_leave_the_in_flight_cell_unreusable(
    qapp, tmp_path
):
    """The guard above has to survive more than one wipe. Two deliberate tissue
    swaps in a row is the ordinary case, and newSliceBtn is never disabled
    during a run, so an accidental double-click delivers two clicked signals on
    its own -- and either way the cell still running on the first slice's tissue
    has yet to announce its finish when the second wipe lands.

    Driven through the real button rather than newSlice() directly, since a
    double-click is the accidental half of what this covers.
    """
    win = _makeWindow(tmp_path)
    try:
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        # Both clicks land while the cell is in the orchestrator's hand, from
        # inside its own protocol; it finishes on the first slice's tissue when
        # that protocol returns, as newSlice()'s docstring says it is allowed to.
        def run(ctx, **kwargs):
            win.newSliceBtn.click()
            win.newSliceBtn.click()

        win.orchestrator.protocolFile.run = run

        win.orchestrator.run_sync()

        assert win.cellPanel.cellList.count() == 0
        assert win.cellPanel.disposition(cell) is None
        assert win.cellPanel.isAttempted(cell) is False
        assert not win.cellPanel.checkAllCompletedBtn.isEnabled()
    finally:
        win.teardown()


def test_new_slice_clears_the_producer(qapp, tmp_path):
    # The producer closes over the slice it was built from; leaving it
    # installed after that slice is discarded would keep surveying tissue
    # the operator has already declared gone.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    assert win.orchestrator._cellProducer is not None

    win.newSlice()

    assert win.orchestrator._cellProducer is None


def test_new_slice_detaches_the_producer_before_clearing_the_queue(qapp, tmp_path):
    """newSlice() must clear the producer before clearing the queue: a refill
    still in flight on the worker thread reads the producer and enqueues its
    result as two separate steps (Orchestrator._refillQueue), so clearing the
    queue first leaves a window where that in-flight refill can still land
    one more old-slice tile in it after the operator has already declared the
    tissue gone.

    Deterministic rather than timing-dependent: clearQueue() is wrapped to
    record whether the producer had already been detached by the time it
    runs, exposing whichever order newSlice() actually calls the two methods
    in without needing a second thread."""
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    orch = win.orchestrator
    assert orch._cellProducer is not None

    producerAlreadyClearedWhenQueueCleared = []
    realClearQueue = orch.clearQueue

    def spyingClearQueue():
        producerAlreadyClearedWhenQueueCleared.append(orch._cellProducer is None)
        realClearQueue()

    orch.clearQueue = spyingClearQueue

    win.newSlice()

    assert producerAlreadyClearedWhenQueueCleared == [True]


def test_start_installs_a_producer_when_a_slice_has_a_region(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()

    win._onStartRun()

    assert win.orchestrator._cellProducer is not None


def test_start_installs_no_producer_without_a_slice(qapp, tmp_path):
    # No slice means no tissue to survey: the run must be a plain queue drain
    # of whatever the operator seeded by hand, not an error.
    win = _makeWindow(tmp_path)
    win._onStartRun()
    assert win.orchestrator._cellProducer is None


def test_start_installs_no_producer_for_a_slice_with_no_region(qapp, tmp_path):
    # A slice with nowhere to look would have its producer report exhaustion on
    # the first call, so installing one only adds a pointless refill round trip.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win._onStartRun()
    assert win.orchestrator._cellProducer is None


def test_start_clears_a_stale_producer_once_the_slice_is_gone(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    assert win.orchestrator._cellProducer is not None

    win.slice = None
    win._onStartRun()

    assert win.orchestrator._cellProducer is None


class _CountingCameraSelector(Qt.QWidget):
    """Like _CountingPipetteSelector, but for the camera: counts
    getSelectedObj() calls and allows swapping the "selection" mid-test, so a
    test can prove _onStartRun re-resolves the camera (and its scope) rather
    than reusing whatever was cached from an earlier Start."""

    def __init__(self, camera):
        super().__init__()
        self._camera = camera
        self.callCount = 0

    def getSelectedObj(self):
        self.callCount += 1
        return self._camera

    def setCamera(self, camera) -> None:
        self._camera = camera


def test_camera_and_scope_are_re_resolved_on_every_start_not_cached(qapp, tmp_path):
    """_onStartRun's docstring promises the camera and scope are re-resolved
    on every Start, so the selection may change between runs. An operator who
    switches the selected camera between runs must have the next run driven
    by the new one, not a stale reference cached from an earlier Start."""
    first = _FakeCamera()
    selector = _CountingCameraSelector(first)
    win = _makeWindow(tmp_path, cameraSelector=selector)
    win.newSlice()
    win.addRegionHere()

    win._onStartRun()
    assert win._cachedCamera is first
    assert win._cachedScope is first.scopeDev

    second = _FakeCamera()
    selector.setCamera(second)
    win._onStartRun()

    assert win._cachedCamera is second
    assert win._cachedScope is second.scopeDev


def test_start_installs_a_producer_for_the_current_slice_not_a_stale_one(
    qapp, tmp_path
):
    """_installCellProducer must build its producer from self.slice at the
    moment Start is pressed, not from whichever slice an earlier Start
    captured. newSlice() replacing a slice that already had a region (so the
    survey check can't short-circuit the way it does when self.slice is None)
    must have the next Start's producer survey the new slice, not the one it
    replaced."""
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    firstSlice = win.slice
    win._onStartRun()
    assert win.orchestrator._cellProducer is not None

    win.newSlice()
    win.addRegionHere()
    secondSlice = win.slice
    assert secondSlice is not firstSlice

    win._onStartRun()

    producer = win.orchestrator._cellProducer
    assert producer is not None
    assert producer._slice is secondSlice


def test_clicking_start_installs_a_producer(qapp, tmp_path):
    """Every other producer test drives _onStartRun() directly, which would
    still pass even if the real Start button stopped calling it. This one
    drives the actual UI path -- clicking Start -- to prove the install is
    still wired to it. The orchestrator's own start() is stubbed out so this
    test exercises only the onStart hook, not a real run (which would need a
    working camera/detector stack this window's fakes don't provide)."""
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win.orchestrator.start = lambda: None

    win.statusPanel.startBtn.click()

    assert win.orchestrator._cellProducer is not None


def test_teardown_clears_the_producer(qapp, tmp_path):
    # The producer closes over the camera and scope devices; leaving it
    # installed on a released orchestrator keeps them reachable from an object
    # the window has stopped managing.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    orch = win.orchestrator

    win.teardown()

    assert orch._cellProducer is None


def test_loading_a_second_protocol_clears_the_outgoing_producer(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    outgoing = win.orchestrator

    _write_protocol(str(tmp_path), "second.py", _NOOP_PROTOCOL)
    # refreshFileList is the discovery scan the picker's popup runs; it lists the
    # newly written file without force-reloading the one already loaded.
    win.protocolPanel.refreshFileList()
    win.protocolPanel.fileCombo.setCurrentText("second")

    assert outgoing._cellProducer is None
    assert win.orchestrator is not outgoing


def test_editing_the_constraints_reaches_the_live_slice(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.searchPanel.minHealthSpin.setValue(0.85)
    assert win.slice.constraints.min_health == pytest.approx(0.85)


def test_invalid_constraints_leave_the_slice_alone(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    before = win.slice.constraints
    win.searchPanel.farDepthSpin.setValue(win.searchPanel.nearDepthSpin.value())
    assert win.slice.constraints is before


def test_the_survey_readout_follows_the_slices_coverage(qapp, tmp_path):
    # Coverage advances on the worker thread as tiles are imaged, so the readout
    # is refreshed off the status signal rather than polled.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    total = len(win.slice.tileGrid())
    win.slice.markCovered(win.slice.nextTile())

    win.statusPanel.sigStatusChanged.emit("surveying")

    assert f"1/{total}" in win.searchPanel.surveyLabel.text()


# acq4.modules.Autopatch's __init__.py does `from .Autopatch import Autopatch`,
# which re-exports the Module subclass under the same name as the submodule and
# shadows it on the package: a dotted-string monkeypatch target
# ("acq4.modules.Autopatch.Autopatch.prompt") resolves attribute-by-attribute and
# lands on that class rather than the submodule, so `prompt` isn't found there.
# importlib.import_module goes through sys.modules instead and reaches the
# actual submodule, where AutopatchWindow._onTissueMoved's module-level `prompt`
# name lives.
_autopatchModule = importlib.import_module("acq4.modules.Autopatch.Autopatch")


def _sliceWithCoveredTiles(win):
    """Install a Slice on `win` with one fully-covered region at a realistic,
    non-square stage coordinate, seed a cell inside its first tile, enqueue a
    second cell on the orchestrator, and return (slice, cell, ctx).

    Built directly rather than through win.newSlice()/addRegionHere(): those
    size the region off the fake camera's micrometre-scale field of view,
    which cannot expose the millimetre-magnitude float error a real stage
    position can. Not origin-centered and not square, for the same reason.
    """
    slice_ = Slice(fov=(20e-6, 10e-6))
    slice_.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    for tile in slice_.tileGrid():
        slice_.markCovered(tile)
    win.slice = slice_

    tile = slice_.tileGrid()[0]
    cell = Cell(Point([tile[0], tile[1], -30e-6], "global"))
    secondCell = Cell(Point([tile[0] + 5e-6, tile[1], -30e-6], "global"))
    win.orchestrator.enqueue(secondCell)

    return slice_, cell, ExecutionContext(cell=cell)


def _sliceWithTodoTiles(win):
    """Install a Slice on `win` with one region and nothing yet covered.

    Built directly rather than through win.newSlice()/addRegionHere(), the same
    reason _sliceWithCoveredTiles gives: those size the region off the fake
    camera's micrometre field of view, which cannot expose millimetre-magnitude
    float error. Asymmetric fov and a non-origin position for the same reason.
    """
    slice_ = Slice(fov=(20e-6, 10e-6))
    slice_.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    win.slice = slice_
    return slice_


def test_tissue_moved_rescans_and_clears_the_queue_on_the_first_answer(win, monkeypatch):
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Rescan the slice"
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    # Primed True so the post-call assertion below actually distinguishes
    # "cleared by the rescan handler" from "left at its untouched default".
    win.orchestrator._producerExhausted = True

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert slice_.coveredTiles == []
    assert win.orchestrator.pendingCells() == []
    assert win.orchestrator._producerExhausted is False


def test_tissue_moved_leaves_everything_alone_on_the_second_answer(win, monkeypatch):
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Skip this cell only"
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    coveredBefore = list(slice_.coveredTiles)
    pendingBefore = win.orchestrator.pendingCells()

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert slice_.coveredTiles == coveredBefore
    assert win.orchestrator.pendingCells() == pendingBefore


def test_tissue_moved_ends_the_cell_on_both_answers(win, monkeypatch):
    for answer in ("Rescan the slice", "Skip this cell only"):
        monkeypatch.setattr(_autopatchModule, "prompt", lambda ctx, **kw: answer)
        _slice, cell, ctx = _sliceWithCoveredTiles(win)
        with pytest.raises(AdvanceToNextCell):
            win._onTissueMoved(cell, ctx, "no features")


def test_tissue_moved_keeps_attempted_cells_in_the_density_record(win, monkeypatch):
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Rescan the slice"
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    tile = slice_.tileGrid()[0]
    win.cellPanel._onCellFinished(cell, "done")
    slice_.registerCells([cell])

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert cell in slice_.cellsNearTile(tile)


def test_tissue_moved_rescan_discards_the_queued_cells_rows(win, monkeypatch):
    """The prompt tells the operator the queued cells are discarded; their
    rows in Area 5 must actually go, or the operator sees the opposite of
    what they just agreed to -- cells still listed as queued."""
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Rescan the slice"
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    queued = _makeCell()
    win.cellPanel.addCell(queued)
    win.orchestrator.enqueue(queued)
    assert win.cellPanel.cellList.count() == 1

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert win.cellPanel.cellList.count() == 0


def test_tissue_moved_rescan_still_reports_its_own_cells_disposition(win, monkeypatch):
    """The rescan branch clears the same queue newSlice() clears, but it means
    "the tissue moved", not "the tissue is gone": the cell that lost tracking has
    to keep reporting its terminal disposition. That disposition is what puts its
    row in Area 5 as the operator's session record and what keeps it attempted --
    and therefore in the tissue density record, so the rescan does not re-detect
    and re-patch it.

    So Orchestrator.abandonCellInHand() must stay out of clearQueue(), where a
    later "simplification" would naturally put it. Driven through a real run loop
    with the cell genuinely in hand, from inside its own protocol, since that is
    the only place the suppression could reach it.
    """
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Rescan the slice"
    )
    slice_, cell, _ctx = _sliceWithCoveredTiles(win)
    # The helper's own spare cell is dropped and the queue rebuilt here so the
    # cell asserted on below is the one the run actually pops, with a second cell
    # genuinely queued behind it for the rescan to discard.
    win.orchestrator.clearQueue()
    queued = _makeCell()
    for c in (cell, queued):
        win.cellPanel.addCell(c)
        win.orchestrator.enqueue(c)

    def run(ctx, **kwargs):
        # Never returns: _onTissueMoved ends the cell via ctx.next_cell(), which
        # _processCell reports as "skipped".
        win._onTissueMoved(ctx.cell, ctx, "no features")

    win.orchestrator.protocolFile.run = run

    win.orchestrator.run_sync()

    assert win.cellPanel.disposition(cell) == "skipped"
    assert win.cellPanel.isAttempted(cell) is True
    # The cell that lost tracking keeps its row; the one merely queued behind it
    # is the one the operator agreed to discard.
    assert win.cellPanel.cellList.count() == 1
    assert win.cellPanel.disposition(queued) is None


def test_tissue_moved_rescan_keeps_an_attempted_cells_row(win, monkeypatch):
    """A cell isAttempted() reports as already started keeps its row through
    a rescan even if it is still sitting in the queue (e.g. a retry) -- it is
    the session record, not a stale queued entry, so clearCells()'s
    discard-everything behaviour must not apply to it."""
    monkeypatch.setattr(
        _autopatchModule, "prompt", lambda ctx, **kw: "Rescan the slice"
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    attempted = _makeCell()
    win.cellPanel.addCell(attempted)
    win.cellPanel._onCurrentCell(attempted)
    win.orchestrator.enqueue(attempted)
    assert win.cellPanel.cellList.count() == 1

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert win.cellPanel.cellList.count() == 1
    assert win.cellPanel.isAttempted(attempted) is True


def test_new_slice_creates_a_slice_directory_and_makes_it_current(win):
    win.newSlice()
    assert win.slice.dirHandle is not None
    assert win.slice.dirHandle.info()["dirType"] == "Slice"
    assert win.manager.getCurrentDir() is win.slice.dirHandle


def test_new_slice_discards_nothing_when_the_directory_cannot_be_made(win):
    """Directory creation happens before anything is thrown away, so a failed
    attempt must leave the old slice, the seeded cell's row, and the
    orchestrator's queue exactly as they were.

    win.newSlice() is called once, successfully, before the failure is
    injected: the state asserted unchanged below has to be genuinely populated
    first, or "unchanged" would also describe a window that never started a
    slice at all.
    """
    from acq4.util.HelpfulException import HelpfulException

    win.newSlice()
    oldSlice = win.slice
    assert oldSlice is not None

    cell = _makeCell()
    win.cellPanel.addCell(cell)
    # Primed attempted before the failing call, so the assertion below
    # actually discriminates: isAttempted(cell) is False by default for any
    # cell newSlice() never touches, which would pass whether or not the
    # failed call left this bookkeeping alone.
    win.cellPanel._onCurrentCell(cell)
    win.orchestrator.enqueue(cell)
    assert win.cellPanel.cellList.count() == 1

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()

    assert win.slice is oldSlice
    assert win.cellPanel.cellList.count() == 1
    assert win.cellPanel.isAttempted(cell) is True
    assert win.orchestrator.pendingCells() == [cell]


def test_new_slice_without_a_camera_does_not_repoint_storage(qapp, tmp_path):
    """_startSlice()'s validation must run before create_data_dir(): a failed
    New slice (no camera selected here) must leave the current storage
    directory exactly where it was, not have already created and switched to
    a fresh, empty Slice directory before discovering the camera is missing.
    """
    win = _makeWindow(tmp_path, cameraSelector=_FakeCameraSelector())
    before = win.manager.getCurrentDir()

    win.newSlice()

    assert win.slice is None
    assert win.manager.getCurrentDir() is before


def test_new_slice_lets_a_programming_error_propagate(qapp, tmp_path):
    """create_data_dir raising something other than HelpfulException is a
    programming error (here, because module=None leaves self.manager as None,
    the constructor's documented headless/test mode) -- not storage guidance
    for the operator -- so it must propagate rather than being swallowed into
    Area 2's error line."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraWithDevice(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    with pytest.raises(AttributeError):
        win.newSlice()


def test_new_slice_reports_a_missing_storage_directory_as_an_instruction(win):
    # The likeliest first use of New slice is by an operator who has not chosen
    # a storage directory. They get an instruction in Area 3, and Area 2's error
    # line -- which is about the search constraints -- stays out of it.
    from acq4.util.HelpfulException import HelpfulException

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()

    assert "Storage directory" in win.statusPanel.instruction()
    assert "Storage directory" not in win.searchPanel.errorLabel.text()


def test_a_successful_new_slice_retracts_the_instruction(win):
    # The instruction says what to do next; once it has been done it is a lie.
    from acq4.util.HelpfulException import HelpfulException

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    original = win.manager.getCurrentDir
    win.manager.getCurrentDir = boom
    win.newSlice()
    assert win.statusPanel.instruction() != ""

    win.manager.getCurrentDir = original
    win.newSlice()

    # storage outranks imagery, so the imagery instruction showing is proof the
    # storage slot is empty -- not merely that the band is.
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION


def test_add_region_here_does_not_create_a_directory(win):
    # A button labelled "add region" must not silently repoint where every
    # subsequent write lands.
    win.addRegionHere()
    assert win.slice.dirHandle is None


def test_area_2_is_locked_until_a_slice_exists(win):
    assert not win.searchPanel.nearDepthSpin.isEnabled()
    win.newSlice()
    assert win.searchPanel.nearDepthSpin.isEnabled()


def test_a_run_in_flight_locks_area_5s_reuse_button(qapp, tmp_path):
    """The reuse gate rides StatusPanel.sigInteractionLocked, the same signal
    Areas 2 and 4 lock on -- a permanent widget-tree connection, so no protocol
    load or teardown can leave it wired to a stale orchestrator."""
    win = _makeWindow(tmp_path)
    try:
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.cellPanel._onCellFinished(cell, "done")
        win.cellPanel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
        assert win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("running")
        assert not win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("surveying")
        assert not win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("waiting")
        assert win.cellPanel.reuseCheckedCellsBtn.isEnabled()
    finally:
        win.teardown()


_RAISING_PROTOCOL = '''
def run(ctx):
    raise RuntimeError("protocol blew up")
'''


def test_start_is_enabled_again_after_a_run_that_ends_in_error(qapp, tmp_path):
    """An operator whose run died must be able to press Start again -- e.g.
    after reusing the cells it never got to. That works only because
    _runLoopBody's finally emits "waiting" *after* _processCell emits "error",
    and "error" on its own disables Start. Asserted through the real
    orchestrator rather than a synthetic sigStatus("waiting").
    """
    from acq4.experiment.exceptions import AbortExperiment

    _write_protocol(tmp_path, "boom.py", _RAISING_PROTOCOL)
    win = _makeWindow(tmp_path)
    try:
        win.protocolPanel.fileCombo.setCurrentText("boom")
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        with pytest.raises(AbortExperiment):
            win.orchestrator.run_sync()

        assert win.statusPanel.startBtn.isEnabled()
    finally:
        win.teardown()


_PASS_MARKING_PROTOCOL = '''
def run(ctx):
    seen = getattr(ctx.cell, "passes_seen", None)
    if seen is None:
        seen = []
        ctx.cell.passes_seen = seen
    seen.append(PASS_NAME)
'''


def test_reused_cells_run_a_second_protocol_as_the_same_objects(qapp, tmp_path):
    """The multi-pass workflow end to end: cellfie every cell in pass 1, load a
    patch protocol, reuse the same cells for pass 2. Identity is the whole
    point -- the same Cell object is what carries its tracker and reference
    stack into pass 2 (design doc 6), which is why this asserts on `is` and on
    state accumulated on the cell itself, not on positions.
    """
    _write_protocol(
        tmp_path, "pass1.py", _PASS_MARKING_PROTOCOL.replace("PASS_NAME", '"one"')
    )
    _write_protocol(
        tmp_path, "pass2.py", _PASS_MARKING_PROTOCOL.replace("PASS_NAME", '"two"')
    )
    win = _makeWindow(tmp_path)
    try:
        win.protocolPanel.fileCombo.setCurrentText("pass1")
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        win.orchestrator.run_sync()

        assert cell.passes_seen == ["one"]
        assert win.cellPanel.disposition(cell) == "done"

        # Loading pass 2 must not silently re-run the completed cell: the reuse
        # button is the deliberate gate.
        win.protocolPanel.fileCombo.setCurrentText("pass2")
        assert win.orchestrator.pendingCells() == []

        win.cellPanel.checkAllCompletedBtn.click()
        win.cellPanel.reuseCheckedCellsBtn.click()

        assert win.orchestrator.pendingCells() == [cell]
        assert win.cellPanel._rows[id(cell)].text() == f"cell {id(cell)} — queued"

        win.orchestrator.run_sync()

        # Same object, so pass 1's accumulated state came along -- this is what
        # makes pass 2 inherit pass 1's reference stack for free.
        assert cell.passes_seen == ["one", "two"]
        assert win.cellPanel.disposition(cell) == "done"
        assert win.cellPanel.isAttempted(cell) is True
    finally:
        win.teardown()


def test_a_new_slice_leaves_area_1_empty_and_live(win):
    # A Slice is fresh tissue with no regions, and Area 1 has to say so: an
    # outline left from the last slice is a coordinate the operator might trust.
    win.addRegionHere()
    assert win.regionPanel.regions()

    win.newSlice()

    assert win.regionPanel.regions() == []
    assert win.regionPanel.addRegionBtn.isEnabled()


def test_seeding_a_region_draws_it_in_area_1(win):
    win.addRegionHere()

    assert len(win.regionPanel.regions()) == 1
    assert win.regionPanel.regions() == win.slice.regions


def test_add_region_here_seeds_a_polygon_when_area_1_asks_for_one(win):
    # PolygonRegion has had no control able to produce it since P2c-1.
    from acq4.experiment.search_region import PolygonRegion

    win.newSlice()
    win.regionPanel.shapeCombo.setCurrentIndex(
        win.regionPanel.shapeCombo.findData("polygon")
    )

    win.addRegionHere()

    region = win.slice.regions[0]
    assert isinstance(region, PolygonRegion)
    # Four corners of the same 3x3-field box the other two shapes get, so the
    # button places a region of a known size whichever shape is selected.
    assert len(region.vertices) == 4
    assert len(win.slice.tileGrid()) > 1


def test_editing_a_region_in_area_1_reaches_the_slice(win):
    win.newSlice()
    edited = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)

    win.regionPanel.sigRegionsChanged.emit([edited])

    assert win.slice.regions == [edited]


def test_editing_a_region_refreshes_the_survey_readout(win):
    # The readout counts tiles over the regions, so an edit that did not refresh
    # it would go on reporting the survey's size for a region that is gone.
    win.newSlice()
    win.addRegionHere()
    before = win.searchPanel.surveyLabel.text()

    win.regionPanel.sigRegionsChanged.emit(
        [RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)]
    )

    assert win.searchPanel.surveyLabel.text() != before


def test_a_region_edit_refreshes_survey_stats_even_when_the_mirror_raises(win):
    # self.slice.setRegions() inside _onRegionsEdited has already committed the
    # edit by the time _cameraMirror.setRegions() runs; a Camera module closed
    # underneath a running session makes that mirror call raise
    # (CameraMirror._redraw() propagates it rather than swallowing it). If the
    # survey refresh ran after the mirror call instead of before, this raise
    # would skip it, and Area 2 would go on advertising the previous edit's
    # tile count -- the operator's only feasibility readout -- for a region
    # that has already changed underneath it, with nothing but a log entry to
    # say so.
    win.newSlice()
    win.addRegionHere()
    before = win.searchPanel.surveyLabel.text()

    def boom(_regions):
        raise HelpfulException("The Camera module is not open.")

    win._cameraMirror.setRegions = boom
    edited = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)

    with pytest.raises(HelpfulException):
        win._onRegionsEdited([edited])

    assert win.slice.regions == [edited]
    assert win.searchPanel.surveyLabel.text() != before


def test_a_region_edit_with_no_slice_is_ignored(win):
    # Area 1's controls are gated on a slice existing, but a signal is not a
    # permission check, and a traceback on the GUI thread is not a second line
    # of defence.
    assert win.slice is None

    win.regionPanel.sigRegionsChanged.emit([])

    assert win.slice is None


def test_area_1_is_locked_until_a_slice_exists(win):
    assert not win.regionPanel.addRegionBtn.isEnabled()

    win.newSlice()

    assert win.regionPanel.addRegionBtn.isEnabled()


def test_a_running_run_locks_area_1(win):
    win.newSlice()

    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("running")

    assert not win.regionPanel.addRegionBtn.isEnabled()


def test_a_paused_run_unlocks_area_1(win):
    # The other side of the gate, wired through the same two window-level
    # connections rather than by calling the panel directly.
    win.newSlice()
    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("running")

    win.statusPanel.sigStatusChanged.emit("paused")

    assert win.regionPanel.addRegionBtn.isEnabled()


def test_the_mirror_checkbox_drives_the_camera_mirror(win):
    win.newSlice()
    win.addRegionHere()

    win.regionPanel.mirrorCheck.setChecked(True)

    assert win._cameraMirror._enabled
    assert win._cameraMirror._regions == win.slice.regions


def test_teardown_takes_the_mirrored_outlines_out_of_the_camera_window(win):
    # Patches _cameraMirror._cameraWindow directly instead of going through
    # _FakeManager's own Camera window, so `drawn` is a recorder scoped to
    # this test alone -- the same idiom the neighboring teardown/release
    # tests use for the same reason.
    drawn = []
    fakeCameraWindow = SimpleNamespace(
        addItem=lambda item, **kwds: drawn.append(item),
        removeItem=drawn.remove,
    )
    win._cameraMirror._cameraWindow = lambda: fakeCameraWindow
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    assert drawn, "nothing was mirrored, so teardown has nothing to prove"

    win.teardown()

    assert drawn == []


def test_a_region_edit_while_locked_is_dropped(win):
    # The panel gates every editing surface it owns, but the window is where an
    # edit becomes the slice's regions, and _onRegionsEdited's own docstring
    # says a signal is not a permission check. This is the second line of that
    # defence: a run is in flight, a producer may be reading the regions on the
    # worker thread, and an edit arriving here anyway is dropped rather than
    # committed.
    win.newSlice()
    win.addRegionHere()
    seeded = list(win.slice.regions)
    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("running")

    win.regionPanel.sigRegionsChanged.emit([RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)])

    assert win.slice.regions == seeded


def test_a_region_edit_while_paused_still_reaches_the_slice(win):
    # The other side: the paused exception is the whole point of the gate, and a
    # window that dropped everything during a run would make it unreachable.
    win.newSlice()
    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("paused")
    edited = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)

    win.regionPanel.sigRegionsChanged.emit([edited])

    assert win.slice.regions == [edited]


def _withPinnedFrameSource(win, hasInterface=True):
    """Point `win` at a Camera window offering one imaging control, and return
    the control it would bind to."""
    source = _FakePinnedFrameSource()

    def getInterfaceForDevice(name):
        if not hasInterface:
            raise KeyError(name)
        return SimpleNamespace(imagingCtrl=source)

    win._cameraWindow = lambda: SimpleNamespace(
        getInterfaceForDevice=getInterfaceForDevice
    )
    return source


def _makePinnedFrame():
    """A minimal stand-in for a real pinned frame.

    win's own PinnedFrameMirror is bound to the same fake pinned-frame source
    these tests mutate, so a "pinned frame" has to be something
    PinnedFrameMirror.refresh() can actually mirror (pg.ImageItem.image/
    transform()/getLevels()/lut/zValue()) -- a plain string satisfies
    ReferenceImagery's own tests (test_reference_imagery.py), which have no
    such mirror in the loop, but raises AttributeError here.
    """
    return pg.ImageItem(np.zeros((2, 2)))


def test_starting_a_slice_mirrors_the_cameras_pinned_frames(win):
    source = _withPinnedFrameSource(win)

    win.newSlice()

    assert win._pinnedFrameMirror._source is source
    # Two, not one: ReferenceImagery.rebind() subscribes to the same signal
    # PinnedFrameMirror does, so a slice with a working camera leaves both
    # listening on the one source.
    assert source.receivers(source.sigPinnedFramesChanged) == 2


def test_teardown_stops_mirroring_the_cameras_pinned_frames(win):
    # The riskier half of the pair CameraMirror already has a teardown test for:
    # this connection lives on the Camera module's own ImagingCtrl, which
    # outlives this window by design, and a live connection on it would go on
    # calling a torn-down window's mirror -- and keep the window reachable.
    source = _withPinnedFrameSource(win)
    win.newSlice()
    # Two: PinnedFrameMirror and ReferenceImagery both subscribed.
    assert source.receivers(source.sigPinnedFramesChanged) == 2

    win.teardown()

    assert source.receivers(source.sigPinnedFramesChanged) == 0
    assert win._pinnedFrameMirror._source is None


def test_a_camera_with_no_imaging_control_stops_the_previous_mirror(win):
    # Switching to a camera the Camera module has no interface for must not
    # leave Area 1 showing the previous camera's frames: those are imagery of
    # different tissue, and regions get drawn over them.
    first = _withPinnedFrameSource(win)
    win.newSlice()
    assert win._pinnedFrameMirror._source is first

    _withPinnedFrameSource(win, hasInterface=False)
    win.newSlice()

    assert win._pinnedFrameMirror._source is None
    assert first.receivers(first.sigPinnedFramesChanged) == 0


def test_a_closed_camera_window_stops_the_previous_mirror(win):
    # The same hazard by the other route: forcing the getter itself to answer
    # None, standing in for the manager-less (headless) case
    # _cameraModuleWindow documents -- not a closed Camera module, which now
    # raises instead and never reaches here, because _canStartSlice() refuses
    # the slice before _startSlice() calls _bindPinnedFrames() at all. What
    # this still proves: _bindPinnedFrames() unbinds the previous source
    # unconditionally, even when the getter it calls next answers None rather
    # than a window.
    first = _withPinnedFrameSource(win)
    win.newSlice()
    assert win._pinnedFrameMirror._source is first

    win._cameraWindow = lambda: None
    win.newSlice()

    assert win._pinnedFrameMirror._source is None
    assert first.receivers(first.sigPinnedFramesChanged) == 0


def test_new_slice_offers_to_clear_the_pinned_frames(win, monkeypatch):
    old = _makePinnedFrame()
    win.manager.pinnedFrameSource.pinnedFrames = [old]
    asked = []
    monkeypatch.setattr(
        win._referenceImagery, "_prompt", lambda text: asked.append(text) or True
    )

    win.newSlice()

    assert len(asked) == 1
    assert win.manager.pinnedFrameSource.pinnedFrames == []


def test_declining_leaves_the_pinned_frames(win, monkeypatch):
    old = _makePinnedFrame()
    win.manager.pinnedFrameSource.pinnedFrames = [old]
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: False)

    win.newSlice()

    assert win.manager.pinnedFrameSource.pinnedFrames == [old]


def test_a_slice_with_no_imagery_asks_for_frames(win, monkeypatch):
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)

    win.newSlice()

    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION


def test_pinning_a_frame_clears_the_band(win, monkeypatch):
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)
    win.newSlice()

    win.manager.pinnedFrameSource.pinnedFrames.append(_makePinnedFrame())
    win.manager.pinnedFrameSource.sigPinnedFramesChanged.emit()

    assert win.statusPanel.instruction() == ""


def test_a_storage_failure_outranks_the_imagery_instruction(win, monkeypatch):
    # Both slots filled at once, which is reachable because create_data_dir can
    # fail with the previous slice still installed.
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)
    win.newSlice()
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    # Not a monkeypatch.setattr("acq4.modules.Autopatch.Autopatch.create_data_dir", ...)
    # string patch: acq4/modules/Autopatch/__init__.py does
    # `from .Autopatch import Autopatch`, so that dotted path resolves to the
    # re-exported Module subclass rather than the Autopatch.py module, and
    # pytest's import-path resolution fails looking for create_data_dir as a
    # class attribute. Failing manager.getCurrentDir() is what create_data_dir
    # itself calls unguarded, and is the same route the other storage-failure
    # tests in this file use.
    monkeypatch.setattr(win.manager, "getCurrentDir", boom)
    win.newSlice()

    assert "Storage directory" in win.statusPanel.instruction()


class _ReentrantOrchestrator:
    """An orchestrator whose bounded wait runs `duringWait`.

    Not a contrivance: _stopAndReleaseOrchestrator waits with updates=True,
    which deliberately pumps the Qt event loop, and teardown() calls it with the
    window still visible and every Area 1 control still connected. Anything the
    operator clicks in those five seconds lands exactly here.
    """

    def __init__(self, duringWait):
        self._duringWait = duringWait
        self.producer = "installed"

    def stop(self):
        pass

    def wait(self, timeout=None, updates=False):
        self._duringWait()

    def setCellProducer(self, producer):
        self.producer = producer

    def setParent(self, parent):
        pass


def test_teardown_cannot_be_re_armed_by_a_click_during_its_wait(win):
    # New slice during that window is the worst of them: it would build a fresh
    # Slice and re-connect PinnedFrameMirror to the Camera module's long-lived
    # ImagingCtrl, and _tornDown is already True by then, so closeEvent returns
    # early and none of it is ever cleaned up again.
    source = _withPinnedFrameSource(win)
    win.statusPanel.unbindOrchestrator()
    win.cellPanel.unbindOrchestrator()
    win.orchestrator = _ReentrantOrchestrator(win.newSlice)

    win.teardown()

    assert win.slice is None
    assert win._pinnedFrameMirror._source is None
    assert source.receivers(source.sigPinnedFramesChanged) == 0


def test_teardown_cannot_be_re_armed_by_add_region_here_during_its_wait(win):
    # The same window, through the other control that can build a slice.
    source = _withPinnedFrameSource(win)
    win.statusPanel.unbindOrchestrator()
    win.cellPanel.unbindOrchestrator()
    win.orchestrator = _ReentrantOrchestrator(win.addRegionHere)

    win.teardown()

    assert win.slice is None
    assert win._pinnedFrameMirror._source is None
    assert source.receivers(source.sigPinnedFramesChanged) == 0


def test_teardown_cannot_be_handed_a_region_edit_during_its_wait(win):
    # An ROI drag released during that wait: the panel is still editable by its
    # own rules -- there is a slice and no run -- so only the window's own
    # torn-down check stops the edit being committed to a slice whose session
    # has ended.
    win.newSlice()
    win.addRegionHere()
    seeded = list(win.slice.regions)
    win.statusPanel.unbindOrchestrator()
    win.cellPanel.unbindOrchestrator()
    win.orchestrator = _ReentrantOrchestrator(
        lambda: win.regionPanel.sigRegionsChanged.emit(
            [RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)]
        )
    )

    win.teardown()

    assert win.slice.regions == seeded


def test_teardown_releases_the_camera_mirror_after_its_wait_not_before(win):
    # Mirror to Camera is not gated on _tornDown -- it is a display preference,
    # not a slice -- so a click on it during teardown's wait genuinely draws
    # outlines into the Camera module's window. Releasing the mirrors after the
    # orchestrator rather than before is what takes those back out; the other
    # order leaves a closed session's graphics in a window that outlives it.
    drawn = []
    fakeCameraWindow = SimpleNamespace(
        addItem=lambda item, **kwds: drawn.append(item),
        removeItem=drawn.remove,
    )
    win._cameraMirror._cameraWindow = lambda: fakeCameraWindow
    win.newSlice()
    win.addRegionHere()
    win.statusPanel.unbindOrchestrator()
    win.cellPanel.unbindOrchestrator()
    win.orchestrator = _ReentrantOrchestrator(
        lambda: win.regionPanel.mirrorCheck.setChecked(True)
    )

    win.teardown()

    assert drawn == []


def test_a_raise_while_stopping_the_orchestrator_still_releases_the_mirrors(win):
    # The mirrors are the only part of teardown that reaches outside this
    # window: their items live in the Camera module's window and their
    # connection on its imaging control, both of which outlive the session. If
    # stopping the orchestrator raises, releasing them is exactly what must
    # still happen -- otherwise a closed session's outlines stay in a window
    # nobody will clean up.
    drawn = []
    fakeCameraWindow = SimpleNamespace(
        addItem=lambda item, **kwds: drawn.append(item),
        removeItem=drawn.remove,
    )
    win._cameraMirror._cameraWindow = lambda: fakeCameraWindow
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    assert drawn, "nothing was mirrored, so teardown has nothing to release"
    win.statusPanel.unbindOrchestrator()
    win.cellPanel.unbindOrchestrator()

    def boom(_orchestrator):
        raise RuntimeError("stop failed")

    win._stopAndReleaseOrchestrator = boom

    with pytest.raises(RuntimeError, match="stop failed"):
        win.teardown()

    assert drawn == []


def test_the_camera_window_getter_finds_a_loaded_camera_module(win):
    cameraWindow = SimpleNamespace()
    win.manager.listModules = lambda: ["Camera", "Data Manager"]
    win.manager.getModule = lambda name: SimpleNamespace(window=lambda: cameraWindow)

    assert win._cameraWindow() is cameraWindow


def test_the_camera_window_getter_raises_when_the_module_is_closed(win, monkeypatch):
    # The Autopatch module opens the Camera module at startup. A module
    # closed afterwards is an error, not a state to degrade into -- a blank
    # Area 1 with regions being drawn over nothing is worse than a raise.
    loaded = []

    def getModule(name):
        loaded.append(name)
        return SimpleNamespace(window=SimpleNamespace)

    monkeypatch.setattr(win.manager, "listModules", lambda: ["Data Manager"])
    monkeypatch.setattr(win.manager, "getModule", getModule)

    with pytest.raises(HelpfulException, match="Camera"):
        win._cameraWindow()

    # Manager.getModule loads a module that is not already open, and this
    # getter is called on every mirror redraw -- including from "Add region
    # here". A button that adds a region must not also start the Camera
    # module: listModules() is checked first, so a module reported closed is
    # never handed to getModule() at all.
    assert loaded == []


def test_the_camera_window_getter_raises_when_the_module_has_no_window(win, monkeypatch):
    monkeypatch.setattr(win.manager, "getModule", lambda name: SimpleNamespace(window=lambda: None))

    with pytest.raises(HelpfulException, match="Camera"):
        win._cameraWindow()


def test_the_default_fake_manager_offers_a_camera_module(win):
    # Production guarantees a Camera module: the Autopatch module opens one at
    # startup. A fake that reports none does not reproduce production, and the
    # None-returning path it stands for is deleted in this branch.
    window = win._cameraWindow()

    assert window is not None
    assert window.getInterfaceForDevice("cam").imagingCtrl is not None


# 200 x 150 fields of the fake camera's 12 x 8 um ROI: 30,000 tiles, past the
# 20,000-tile cap. Asymmetric in both axes and at a realistic stage coordinate,
# so a guard that read one axis twice would be caught.
_OVERSIZED_REGION = RectRegion(1e-3, 2e-3, 1e-3 + 2.4e-3, 2e-3 + 1.2e-3)


def test_an_edit_that_would_plan_too_many_tiles_is_refused(win):
    # The defect this exists for: an ROI dragged out to 0.687 m x 0.873 m at a
    # 130 um field planned 35 million tiles, and _refreshSurveyStats runs on
    # every edit -- minutes of frozen GUI per drag.
    win.newSlice()
    win.addRegionHere()
    seeded = list(win.slice.regions)

    win.regionPanel.sigRegionsChanged.emit([_OVERSIZED_REGION])

    assert win.slice.regions == seeded


def test_a_refused_edit_says_why_in_area_3s_band(win):
    # Silently dropping it would leave the operator with an outline on screen
    # that no survey will ever tile.
    win.newSlice()

    win.regionPanel.sigRegionsChanged.emit([_OVERSIZED_REGION])

    message = win.statusPanel.instruction()
    assert "30000" in message.replace(",", "")
    assert "tile" in message


def test_a_refused_edit_snaps_area_1_back_to_the_slices_regions(win):
    # The ROI the operator is still holding has to go back where it was: an
    # outline left at a size the slice refused is a lie about what will be
    # surveyed.
    win.newSlice()
    win.addRegionHere()
    seeded = list(win.slice.regions)

    win.regionPanel.sigRegionsChanged.emit([_OVERSIZED_REGION])

    assert win.regionPanel.regions() == seeded


def test_a_refused_edit_does_not_reach_the_camera_mirror(win):
    # The mirror draws what the slice holds; an outline of the refused shape in
    # the Camera window would be the same lie in the other view.
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    seeded = list(win.slice.regions)

    win.regionPanel.sigRegionsChanged.emit([_OVERSIZED_REGION])

    assert win._cameraMirror._regions == seeded


def test_the_next_good_edit_retracts_the_refusal(win):
    # The message says what to fix; once it has been fixed it is a lie.
    win.newSlice()
    win.regionPanel.sigRegionsChanged.emit([_OVERSIZED_REGION])
    assert win.statusPanel.instruction() != ""

    win.regionPanel.sigRegionsChanged.emit([RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)])

    # region outranks imagery: the imagery instruction showing proves the
    # refusal was retracted.
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION
    assert len(win.slice.regions) == 1


def test_a_refused_edit_does_not_erase_the_storage_instruction(win):
    """Area 3's band has two Area 1 writers with different conditions, and
    neither can see the other's. A region edit retracting its own refusal must
    not also retract newSlice()'s "choose a storage directory", which is still
    just as true as it was."""
    from acq4.util.HelpfulException import HelpfulException

    win.addRegionHere()  # a slice, without going through create_data_dir

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()
    assert "Storage directory" in win.statusPanel.instruction()

    win.regionPanel.sigRegionsChanged.emit([RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)])

    assert "Storage directory" in win.statusPanel.instruction()


def test_add_region_here_reports_a_refusal_rather_than_raising(win):
    """"Add region here" seeds 3x3 fields, which is nine tiles whatever the
    field of view, so it cannot trip the cap as it stands. The refusal is
    caught anyway because a traceback out of a button's slot is not a failure
    mode this window should have at all -- driven here by making the slice
    refuse, since the geometry itself will not."""
    from acq4.experiment.slice import RegionTooLarge

    win.newSlice()

    def refuse(region):
        raise RegionTooLarge("that region would plan 999999 tiles")

    win.slice.addRegion = refuse

    win.addRegionHere()

    assert "999999" in win.statusPanel.instruction()
    assert win.regionPanel.regions() == []


def test_add_region_here_refreshes_survey_stats_even_when_the_mirror_raises(win):
    # slice.addRegion() and regionPanel.setRegions() above have already
    # committed the seeded region by the time _cameraMirror.setRegions() runs;
    # a Camera module closed underneath a running session makes that mirror
    # call raise (CameraMirror._redraw() propagates it rather than swallowing
    # it). If the survey refresh ran after the mirror call instead of before,
    # this raise would skip it, and Area 2 would go on reporting "no region"
    # for a slice that this button just gave nine tiles -- the operator's only
    # feasibility readout, silently stale until the next successful edit.
    win.newSlice()

    def boom(_regions):
        raise HelpfulException("The Camera module is not open.")

    win._cameraMirror.setRegions = boom

    with pytest.raises(HelpfulException):
        win.addRegionHere()

    assert len(win.slice.regions) == 1
    assert win.searchPanel.surveyLabel.text() != "no region"


def test_starting_a_slice_frames_area_1_on_the_camera(win):
    """A fresh pg.ViewBox spans about a metre, and Area 1's units are global
    metres. Left there, an operator's first click in an empty view lands a
    polygon vertex half a metre out -- which is how a region big enough to plan
    35 million tiles gets drawn in the first place.

    Computed off the fake camera directly (its "roi" boundary and centre) so a
    bug in _cameraFov() is caught rather than echoed back."""
    camera = win.cameraSelector.getSelectedObj()
    _, _, fov_w, fov_h = camera.getBoundary(globalCoords=True, mode="roi")
    cx, cy, _ = camera.globalCenterPosition("roi")

    try:
        win.newSlice()

        (vx0, vx1), (vy0, vy1) = win.regionPanel.view.viewRange()
        assert (vx0 + vx1) / 2 == pytest.approx(cx)
        assert (vy0 + vy1) / 2 == pytest.approx(cy)
        # Ten fields across, so the camera's own field is a visible fraction of
        # the view rather than sub-pixel. Aspect lock may widen one axis, so
        # this is the floor on each, and a ceiling well short of the metre the
        # viewport started at.
        assert (vx1 - vx0) >= 10 * fov_w
        assert (vy1 - vy0) >= 10 * fov_h
        assert (vx1 - vx0) < 1e-3
        assert (vy1 - vy0) < 1e-3
    finally:
        win.teardown()


def test_add_region_here_without_a_slice_frames_area_1_too(win):
    # The other route into a slice, and the one an operator is most likely to
    # take first.
    camera = win.cameraSelector.getSelectedObj()
    cx, cy, _ = camera.globalCenterPosition("roi")

    try:
        win.addRegionHere()

        (vx0, vx1), (vy0, vy1) = win.regionPanel.view.viewRange()
        assert (vx0 + vx1) / 2 == pytest.approx(cx)
        assert (vy0 + vy1) / 2 == pytest.approx(cy)
    finally:
        win.teardown()


def test_no_outlines_appear_when_the_checkbox_is_not_ticked(win):
    # A region is not a reason to start mirroring something the operator never
    # asked to mirror.
    win.newSlice()

    win.addRegionHere()

    assert win.manager.drawn == []


def test_a_headless_window_with_no_manager_still_starts_a_slice(qapp, tmp_path):
    # module=None is a mode the constructor supports by design -- the parameter
    # defaults to None (see AutopatchWindow.__init__'s signature; it carries no
    # docstring saying so) -- and with no manager there is nothing to listen to,
    # which must not be an error.
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraWithDevice(),
    )
    try:
        win.protocolPanel.fileCombo.setCurrentText("demo")
        assert win._startSlice() is True
    finally:
        win.teardown()


def test_unticking_the_mirror_takes_the_outlines_down(win):
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    assert win.manager.drawn != []

    win.regionPanel.mirrorCheck.setChecked(False)

    assert win.manager.drawn == []


def test_a_seeded_cell_gets_a_marker(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)

    win.cellPanel.addCell(cell)

    assert len(win._progressOverlay.scatter.getData()[0]) == 1


def test_marker_position_comes_from_initial_position_not_position(qapp, win):
    """cell.position evaluates max(self._positions), iterating a dict the
    tracking worker writes. initialPosition is assigned once and never
    mutated, so it is the only safe read on the GUI thread.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)

    win.cellPanel.addCell(cell)

    x, y = win._progressOverlay.scatter.getData()
    assert x[0] == pytest.approx(1.0e-3)
    assert y[0] == pytest.approx(2.0e-3)


def test_a_finished_cell_is_recoloured(qapp, win):
    """Also kills the mutant that always paints with densityBrushes regardless
    of the selected source: that mutant changes the colour too, but not to the
    success source's "done" colour, which is checked here by name."""
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    win.cellPanel._onCellFinished(cell, "done")

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    assert after != before
    expected = successBrushes(win._colorContext())[id(cell)].color().name()
    assert after == expected


def test_changing_the_colour_source_recolours_without_a_run(qapp, win):
    """Also kills the mutant that refreshes with some other source, or ignores
    the selection entirely: either would still change the colour, but not to
    the health source's colour for this cell's score, which is checked here by
    name."""
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    cell.score = 0.9
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    index = [k for _l, k, _f in COLOR_SOURCES].index("health")
    win.regionPanel.colorCombo.setCurrentIndex(index)

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    assert after != before
    expected = healthBrushes(win._colorContext())[id(cell)].color().name()
    assert after == expected


def test_a_cell_the_orchestrator_has_started_draws_in_the_in_flight_colour(qapp, win):
    """The two colour tests above both compute `expected` from
    win._colorContext() itself, so a defect inside the join between
    CellPanel.isAttempted() and _colorContext()'s own `attempted` set is
    invisible to them by construction -- setting `attempted=set()` in
    _colorContext() still passes both, since their "expected" brush is drawn
    from that same broken set.

    "Attempted" is driven the way production drives it: the orchestrator's own
    sigCurrentCell signal, which CellPanel._onCurrentCell answers by adding the
    cell to its _attempted set -- not by writing into that private set
    directly. win.orchestrator is a real, bound Orchestrator (see the `win`
    fixture), so this is the identical signal a real run emits just before
    handing the protocol its context; emitting it here only skips the worker
    thread, not the announcement path.

    _refreshProgress() is called explicitly rather than waited for: nothing
    in this window currently re-draws Area 1 at the moment a cell's run
    starts (StatusPanel's own sigStatusChanged("running") is not among the
    statuses _onRunStatus() redraws on), which is a gap in when the operator
    sees blue, not in what blue means once drawn -- the seam this test pins.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    win.orchestrator.sigCurrentCell.emit(cell)
    win._refreshProgress()

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    independent = ColorContext(
        cellIds=[id(cell)],
        positions={},
        dispositions={},
        attempted={id(cell)},
        scores={},
        fov=None,
        tileVolume=None,
        maxCellDensity=None,
        minHealth=None,
    )
    expected = successBrushes(independent)[id(cell)].color().name()
    assert after != before
    assert after == expected


def test_the_in_flight_colour_appears_without_any_other_refresh(qapp, win):
    """The test above calls win._refreshProgress() itself, so it cannot tell
    whether anything in the window actually asks for that redraw on its own --
    it would pass identically if nothing ever did. This test never calls
    _refreshProgress() (nor _onRunStatus(), nor anything else that redraws
    Area 1): the only thing that happens between seeding the cell and reading
    its marker is the orchestrator's own sigCurrentCell announcement, which is
    exactly what a real run does the instant it takes a cell off the queue.

    If the marker is still grey afterward, the operator's one load-bearing cue
    -- the blue dot that says "the orchestrator is working on this cell right
    now" -- never appears during a run, since nothing else redraws Area 1
    between "surveying"/"waiting" statuses either.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    win.orchestrator.sigCurrentCell.emit(cell)

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    independent = ColorContext(
        cellIds=[id(cell)],
        positions={},
        dispositions={},
        attempted={id(cell)},
        scores={},
        fov=None,
        tileVolume=None,
        maxCellDensity=None,
        minHealth=None,
    )
    expected = successBrushes(independent)[id(cell)].color().name()
    assert after != before
    assert after == expected


def test_the_legend_follows_the_colour_source(qapp, win):
    # A slice is required here: _densityLegend only reports "At the density
    # cap" once tileVolume and maxCellDensity are both known (_colorContext
    # leaves them None with no slice), and without one it falls back to the
    # raw "10+ per field" label instead.
    _sliceWithTodoTiles(win)
    index = [k for _l, k, _f in COLOR_SOURCES].index("density")
    win.regionPanel.colorCombo.setCurrentIndex(index)

    assert win.regionPanel.legendLabels() == ["Sparse", "At the density cap"]


def test_coverage_draws_the_todo_tiles_not_the_covered_ones(qapp, win):
    """Also kills the mutant that unconditionally drops a fixed index (e.g.
    grid[0]) instead of filtering on what is actually covered: covering a
    tile that is deliberately not grid[0] leaves that mutant's count still
    matching, but its rectangles centred on the wrong tiles."""
    _sliceWithTodoTiles(win)
    grid = win.slice.tileGrid()
    coveredIndex = len(grid) // 2
    covered = grid[coveredIndex]
    win.slice.markCovered(covered)

    win._onRunStatus("waiting")

    items = win._progressOverlay.coverageItems()
    assert len(items) == len(grid) - 1
    # setCoverage's rects are built from (cx - fovW/2, cy - fovH/2, fovW, fovH)
    # in the view's own coordinates, so a rect's centre recovers the tile it
    # was drawn for.
    actualCentres = sorted(
        (item.rect().center().x(), item.rect().center().y()) for item in items
    )
    expectedCentres = sorted(
        tuple(tile) for i, tile in enumerate(grid) if i != coveredIndex
    )
    assert len(actualCentres) == len(expectedCentres)
    for (ax, ay), (ex, ey) in zip(actualCentres, expectedCentres):
        assert ax == pytest.approx(ex)
        assert ay == pytest.approx(ey)


def test_a_tracked_cell_marker_follows_its_position_signal(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)

    cell.sigPositionChanged.emit(Point([1.4e-3, 2.1e-3, -30e-6], "global"))

    x, y = win._progressOverlay.scatter.getData()
    assert x[0] == pytest.approx(1.4e-3)
    assert y[0] == pytest.approx(2.1e-3)


def test_refresh_never_iterates_the_tracked_positions_dict(qapp, win):
    """_syncCellPositions must seed a cell's marker from cell.initialPosition,
    never from cell.position: Cell.position evaluates max(self._positions),
    which iterates a dict the tracking worker thread writes to, so a
    GUI-thread read racing an insert raises RuntimeError: dictionary changed
    size during iteration.

    The trap -- a _positions dict that raises on both __iter__ and keys() --
    must be armed *before* the cell is ever added to the panel: addCell()
    synchronously drives _onCellStateChanged -> _syncCellPositions, which is
    the only place a never-before-seen cell's position is read. Arming it
    afterward would let that one read land on the still-healthy dict, seed
    the cache, and never happen again -- so a mutation to cell.position would
    pass unnoticed, which is exactly what happened before this rewrite.
    Arming first forces the sync to obtain a position from a cell whose
    _positions dict already explodes, so only the correct initialPosition
    read can survive.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)

    class Exploding(dict):
        def __iter__(self):
            raise RuntimeError("dictionary changed size during iteration")

        def keys(self):
            raise RuntimeError("dictionary changed size during iteration")

    cell._positions = Exploding(cell._positions)

    win.cellPanel.addCell(cell)

    xs, ys = win._progressOverlay.scatter.getData()
    assert len(xs) == 1
    assert xs[0] == pytest.approx(cell.initialPosition[0])
    assert ys[0] == pytest.approx(cell.initialPosition[1])


def test_discarding_a_cell_disconnects_it(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)

    win.cellPanel.discardCells([cell])

    assert cell.receivers(cell.sigPositionChanged) == 0


def test_refresh_coverage_after_teardown_does_not_touch_the_overlay(win):
    """A torn-down window must return before it ever calls into the overlay
    again.

    Seeds real coverage items first, then tears the window down: teardown()
    itself now empties the overlay (ProgressOverlay.release() takes every
    item back out of the view, among the rest of its cleanup), so what is
    left to prove is that _refreshCoverage(), called explicitly afterward,
    does not undo that by reaching into the overlay a second time. Against an
    unguarded `if self.slice is None:` (missing the `self._tornDown or`) this
    fails because the still-installed slice's to-do tiles get redrawn -- a
    torn-down window with no slice, and one with a slice, must both leave the
    released overlay empty.
    """
    _sliceWithTodoTiles(win)
    win._onRunStatus("waiting")
    assert win._progressOverlay.coverageItems()

    win.teardown()
    win._refreshCoverage()

    assert win._progressOverlay.coverageItems() == []


def test_clicking_a_marker_selects_that_cell_in_area_5(qapp, win):
    first = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    second = _makeCellAt(1.4e-3, 2.1e-3, -30e-6)
    win.cellPanel.addCell(first)
    win.cellPanel.addCell(second)

    win._progressOverlay.sigMarkerClicked.emit(id(second))

    assert win.cellPanel.cellList.currentItem().data(Qt.Qt.UserRole) is second


def test_a_stale_marker_click_is_ignored(qapp, win):
    """A rescan can discard a cell between the draw and the click.

    Seeds and selects a real cell first: asserting `currentItem() is None` on an
    empty list would be trivially true and would pass for an implementation that
    cleared the selection, or one that raised and was swallowed. The invariant is
    that a stale id neither raises nor moves the operator off the row they chose.
    """
    known = _makeCellAt(1.0e-3, 2.0e-3)
    win.cellPanel.addCell(known)
    win.cellPanel.selectCell(known)

    win._progressOverlay.sigMarkerClicked.emit(123456)

    assert win.cellPanel.cellList.currentItem().data(Qt.Qt.UserRole) is known


def test_zoom_to_cell_frames_area_1_on_it(qapp, win):
    """Also pins the 3x span itself, not just the centre: a centre-only
    assertion cannot tell a correctly-sized viewport from one seeded with the
    wrong multiplier (or a span that ignores the field of view entirely)."""
    _sliceWithTodoTiles(win)
    cell = _makeCellAt(1.4e-3, 2.1e-3, -30e-6)
    win.cellPanel.addCell(cell)
    win.cellPanel.selectCell(cell)

    win.cellPanel.zoomToCellBtn.click()

    fovW, fovH = win.slice.fov
    xRange, yRange = win.regionPanel.view.viewRange()
    assert sum(xRange) / 2 == pytest.approx(1.4e-3, rel=1e-6)
    assert sum(yRange) / 2 == pytest.approx(2.1e-3, rel=1e-6)
    # x is the axis the aspect lock leaves alone in this fixture, so it comes
    # out exactly 3x the field of view; y is the one the lock widens to match
    # the widget's shape, so it can only be bounded below.
    assert xRange[1] - xRange[0] == pytest.approx(3 * fovW, rel=1e-6)
    assert yRange[1] - yRange[0] >= 3 * fovH


def test_fit_to_regions_is_unaffected_by_a_progress_marker(qapp, win):
    """Measured in a real window: fitting a 300x200um region at 1mm from
    origin gave 360x270um with no markers drawn and 27m x 20m, centred near
    global (0, 0), with one. The cause is the progress overlay's
    ScatterPlotItem: pxMode=True keeps its markers a constant *screen* size,
    so its own boundingRect() reports that pixel halo converted into view
    units at whatever scale the view has when it is asked -- and at the
    region's own scale here that conversion is enormous.

    Every fitToRegions() test in test_region_panel.py builds a bare
    RegionPanel with no overlay in its view at all, so none of them can catch
    this; this one needs the real ProgressOverlay a real AutopatchWindow
    attaches, which is why it lives here instead.

    Compared with pytest.approx at a tight relative tolerance rather than
    exact equality: both calls re-run the identical computation over the
    identical region bounds (the marker plays no part in either, once
    correctly excluded), so they are expected to be bit-for-bit identical --
    the tolerance only guards against incidental float non-determinism, not
    against a real difference. Reverting the exclusion in
    RegionPanel._mirroredImageryBounds() reproduces the measured blowup (many
    orders of magnitude), which this tolerance does not come close to
    absorbing.
    """
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.fitToRegions()
    before = win.regionPanel.view.viewRange()

    win.cellPanel.addCell(_makeCellAt(1.0e-3, 2.0e-3, -30e-6))
    win.regionPanel.fitToRegions()

    after = win.regionPanel.view.viewRange()
    (bx0, bx1), (by0, by1) = before
    (ax0, ax1), (ay0, ay1) = after
    assert ax0 == pytest.approx(bx0, rel=1e-9)
    assert ax1 == pytest.approx(bx1, rel=1e-9)
    assert ay0 == pytest.approx(by0, rel=1e-9)
    assert ay1 == pytest.approx(by1, rel=1e-9)


def test_fit_on_an_empty_area_1_leaves_the_view_untouched(qapp, win):
    """Before this branch, an empty progress overlay's scatter made
    RegionPanel._mirroredImageryBounds() return a null QRectF rather than
    None (a scatter with no points still has *a* boundingRect, just an empty
    one), so fitToRegions()'s `if rect is None: return` guard never fired and
    pressing Fit on an empty Area 1 recentred the view on global (0, 0)."""
    before = win.regionPanel.view.viewRange()

    win.regionPanel.fitToRegions()

    assert win.regionPanel.view.viewRange() == before


def test_new_slice_clears_progress_markers_coverage_and_position_connections(win):
    """Measured after newSlice() with one cell and to-do tiles: markers=1,
    coverage=9, _positionConnected=1, _cellPositions=1 -- while
    cellPanel.cells() is already empty -- and the discarded cell still
    reported receivers(sigPositionChanged) == 1: the connection this window
    made kept a Cell CellPanel had already dropped alive, and its connection
    live, contrary to _positionConnected's own comment that it "adds no
    lifetime, only a handle".

    The receivers() assertion is the one that actually exercises the fix: an
    earlier round of this same module found a mandated mutation that a
    dict-emptiness assertion alone did not catch, because a nearby `= None`
    had already broken the reference cycle before this method got a chance
    to (see test_teardown_disconnects_every_cell_position_connection for the
    same reasoning applied to teardown()).
    """
    win.newSlice()
    win.addRegionHere()
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    win._refreshCoverage()

    assert len(win._progressOverlay.scatter.getData()[0]) == 1
    assert win._progressOverlay.coverageItems()
    assert id(cell) in win._cellPositions
    assert id(cell) in win._positionConnected
    assert cell.receivers(cell.sigPositionChanged) == 1

    win.newSlice()

    assert len(win._progressOverlay.scatter.getData()[0]) == 0
    assert win._progressOverlay.coverageItems() == []
    assert win._cellPositions == {}
    assert win._positionConnected == {}
    assert cell.receivers(cell.sigPositionChanged) == 0


def test_a_freshly_built_window_shows_a_meaningful_legend(win):
    """The spec wants an empty plot with a meaningful legend, not a blank
    one: before this branch, _refreshProgress() was never called during
    AutopatchWindow.__init__, so legendLabels() == [] until the first cell or
    colour-source change."""
    assert win.regionPanel.legendLabels() != []
