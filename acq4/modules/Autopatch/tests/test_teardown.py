"""Regression tests for AutopatchWindow.teardown(): the Orchestrator/Cell
QObjects must be unwired from the window's panels (and the orchestrator
stopped) deterministically on close, rather than left for Python's
non-deterministic cyclic GC to eventually reclaim -- which can free live
QObjects outside Qt's safe teardown path and crash the process on exit."""
import gc
import logging
import os
import weakref

import pytest

from acq4.util import Qt


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
    the way a real PatchPipette delegates target lookups to its manipulator."""

    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakeCameraSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


_NOOP_PROTOCOL = '''"""Teardown test fixture: opens and immediately closes one log_action entry.
Used by the weakref/gc proof, which never starts the orchestrator (see that
test's docstring for why) but does run this protocol synchronously via
run_sync_cell(), so the on_log_action wiring this task adds is exercised by
that proof too -- not just resolving immediately without touching ctx."""


def run(ctx, **kwargs):
    with ctx.log_action("Noop") as action_entry:
        action_entry.set_status("doing nothing in particular")
'''

_SLOW_PROTOCOL = '''"""Teardown test fixture: loops until stopped. Used to prove
AutopatchWindow.teardown() actually stops an in-flight run rather than
abandoning it."""
from acq4.util.task import check_stop, sleep


def run(ctx, **kwargs):
    while True:
        check_stop()
        sleep(0.01)
'''


def _write_protocol(path, name, body):
    with open(os.path.join(path, name), "w") as fh:
        fh.write(body)


def test_teardown_breaks_the_orchestrator_cell_window_cycle(qapp, tmp_path):
    """Load a protocol and seed a cell (but do not start the orchestrator --
    see the note below), tear the window down, and prove -- with the cyclic GC
    disabled -- that plain refcounting (no gc.collect()) is enough to free the
    orchestrator, the seeded cell, and the window afterward.

    Before the fix, StatusPanel/CellPanel held live signal connections to the
    Orchestrator (and the Orchestrator/window held references back to them),
    so the whole graph was a genuine reference cycle only the cyclic collector
    could break.

    This deliberately never calls orchestrator.start(): doing so hands the
    orchestrator to gentletask as a ThreadTask whose stored target is a bound
    method of the orchestrator itself (`self._task._fn is orchestrator._runLoopBody`),
    which is its own independent reference cycle -- permanent only while that
    run is in flight, since _onLoopFinished breaks it once the run completes.
    It is unrelated to the window/panel wiring this fix addresses, and out of
    scope here since it lives in acq4/experiment + the separate gentletask
    library. A second test below starts the orchestrator to prove teardown()
    stops an in-flight run; it does not repeat this refcounting proof.
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    gc.disable()
    try:
        win = AutopatchWindow(
            module=None,
            protocolDir=str(tmp_path),
            pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
            cameraSelector=_FakeCameraSelector(),
        )
        win.protocolPanel.fileCombo.setCurrentText("demo")

        win.cellPanel.addFromTargetBtn.click()
        assert win.cellPanel.cellList.count() == 1
        seededCell = list(win.cellPanel._cells.values())[0]
        # Select the row before running so the run below actually populates
        # _timelineItems, making the empty-dict assertions after it meaningful.
        win.cellPanel.cellList.setCurrentRow(0)

        orchestrator = win.orchestrator
        assert orchestrator is not None
        # Sanity check the cycle actually exists pre-teardown: the orchestrator
        # is cross-wired to both panels via signal connections.
        assert win.statusPanel._orchestrator is orchestrator
        assert win.cellPanel._orchestrator is orchestrator

        # Actually run the protocol synchronously (main thread; no gentletask
        # ThreadTask involved, so this does not hit the independent
        # ThreadTask/orchestrator cycle the docstring above rules out of
        # scope), so ctx.log_action() -> CellPanel.onLogAction -> the entry's
        # on_status/on_widget/on_finish callbacks all actually run -- exactly
        # the new reference path this task adds (an ActionLogEntry's
        # callbacks closing over CellPanel) -- before proving the whole graph
        # is still freed by plain refcounting below.
        orchestrator.run_sync_cell(seededCell)
        win.cellPanel.cellList.setCurrentRow(0)
        assert win.cellPanel.timelineList.count() == 1
        assert "Noop" in win.cellPanel.timelineList.item(0).text()
        # No stale per-entry bookkeeping left behind once the entry finished --
        # if onLogAction's wiring held onto the entry itself instead of just
        # its id, this would still show it.
        assert win.cellPanel._entryTimelineLoc == {}
        assert win.cellPanel._timelineItems == {}

        orchestrator_ref = weakref.ref(orchestrator)
        cell_ref = weakref.ref(seededCell)
        window_ref = weakref.ref(win)
        statusPanel_ref = weakref.ref(win.statusPanel)
        cellPanel_ref = weakref.ref(win.cellPanel)

        win.teardown()

        # No panel still references the orchestrator once torn down.
        assert win.statusPanel._orchestrator is None
        assert win.cellPanel._orchestrator is None
        assert win.orchestrator is None
        assert win.cellPanel._cells == {}

        del orchestrator, seededCell
        win.close()  # exercises the closeEvent path too; teardown() is idempotent
        del win
        # No gc.collect() below -- pure refcounting only, since gc is disabled.

        assert orchestrator_ref() is None, "orchestrator should be freed by refcounting alone"
        assert cell_ref() is None, "seeded cell should be freed by refcounting alone"
        assert window_ref() is None, "window should be freed by refcounting alone"
        assert statusPanel_ref() is None, "StatusPanel should be freed by refcounting alone"
        assert cellPanel_ref() is None, "CellPanel should be freed by refcounting alone"
    finally:
        gc.enable()


def test_teardown_frees_the_slice_producer_and_cells_by_refcounting(qapp, tmp_path):
    """The proof above cannot reach the cell-search half of the object graph:
    its camera selector returns None, so no Slice is ever built and no producer
    ever installed. This builds that half -- a slice, a region, a producer
    closing over the camera and scope devices, and a cell run through the
    protocol -- and proves the same thing about all of it: with the cyclic
    collector disabled, plain refcounting frees the window, the slice, the
    producer and the cells.

    The producer is where the risk is: it holds the slice, the orchestrator
    holds the producer, and the orchestrator is parented to the window, so a
    teardown that left the producer installed would keep the slice and both
    devices reachable from an object nothing is looking after any more.

    The camera stand-in comes from test_window_integration rather than being
    copied in here: it is the same mode-sensitive getBoundary/
    globalCenterPosition/scopeDev fake the producer install needs, and a second
    copy would be one more thing to keep in step with acq4's real Camera. The
    manager stand-in is the same: newSlice() needs somewhere real to create a
    Slice directory, and test_window_integration's _FakeManager (backed by an
    actual DirHandle) is that fixture already.
    """
    from types import SimpleNamespace

    import acq4.util.DataManager as dm
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    from .test_window_integration import _FakeCameraWithDevice, _FakeManager

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    storageRoot = dm.getDirHandle(str(tmp_path / "storage"), create=True)

    gc.disable()
    try:
        win = AutopatchWindow(
            module=SimpleNamespace(manager=_FakeManager(storageRoot)),
            protocolDir=str(tmp_path),
            pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
            cameraSelector=_FakeCameraWithDevice(),
        )
        win.protocolPanel.fileCombo.setCurrentText("demo")

        win.newSlice()
        win.addRegionHere()
        assert win.slice is not None
        assert len(win.slice.regions) == 1

        win.cellPanel.addFromTargetBtn.click()
        assert win.cellPanel.cellList.count() == 1
        seededCell = list(win.cellPanel._cells.values())[0]
        # Selected before running so the run below actually populates
        # _timelineItems, the same reason as the proof above.
        win.cellPanel.cellList.setCurrentRow(0)

        # What Start does on the GUI thread: cache the devices and install a
        # producer built from the current slice.
        win._onStartRun()
        producer = win.orchestrator._cellProducer
        assert producer is not None
        assert producer._slice is win.slice

        # And a cell's worth of protocol, inline on this thread (no gentletask
        # ThreadTask, for the reason the first test's docstring gives), so the
        # ctx.log_action wiring runs with the search half of the graph in place.
        win.orchestrator.run_sync_cell(seededCell)
        win.cellPanel.cellList.setCurrentRow(0)
        assert win.cellPanel.timelineList.count() == 1

        sliceState = win.slice
        refs = {
            "orchestrator": weakref.ref(win.orchestrator),
            "producer": weakref.ref(producer),
            "slice": weakref.ref(sliceState),
            "seeded cell": weakref.ref(seededCell),
            "window": weakref.ref(win),
        }

        win.teardown()

        assert win.orchestrator is None
        assert win.cellPanel._cells == {}

        del producer, sliceState, seededCell
        win.close()  # exercises the closeEvent path too; teardown() is idempotent
        del win
        # No gc.collect() below -- pure refcounting only, since gc is disabled.

        for name, ref in refs.items():
            assert ref() is None, f"{name} should be freed by refcounting alone"
    finally:
        gc.enable()


def test_teardown_stops_an_in_flight_orchestrator_run(qapp, qtbot, tmp_path):
    """teardown() must stop a currently-running orchestrator rather than
    abandon it, and leave no panel still bound to it afterward."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "slow.py", _SLOW_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("slow")
    win.cellPanel.addFromTargetBtn.click()

    win.statusPanel.startBtn.click()
    task = win.orchestrator._task
    assert task is not None
    # Give the worker thread a moment to actually enter the slow action's loop.
    qtbot.wait(50)
    assert not task.is_done

    win.teardown()

    assert task.is_done
    assert task.is_stopped
    assert win.orchestrator is None
    assert win.statusPanel._orchestrator is None
    assert win.cellPanel._orchestrator is None

    win.close()


_FAILING_PROTOCOL = """
def run(ctx, **kwargs):
    with ctx.log_action("Boom"):
        raise RuntimeError("protocol blew up")
"""


def test_teardown_frees_everything_after_a_run_error(qapp, tmp_path):
    """A halted run leaves a RunErrorRecord in StatusPanel and traceback text in
    CellPanel. Neither may keep the orchestrator, the cell, or the window alive.

    Both stores hold plain strings by construction, so this is the guard against
    a later change that "helpfully" retains the exception or the ActionLogEntry
    instead -- either of which would put a traceback's frames, and their locals,
    behind a reference only the cyclic GC could reclaim.
    """
    from acq4.experiment.exceptions import AbortExperiment
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "boom.py", _FAILING_PROTOCOL)

    gc.disable()
    try:
        win = AutopatchWindow(
            module=None,
            protocolDir=str(tmp_path),
            pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
            cameraSelector=_FakeCameraSelector(),
        )
        win.protocolPanel.fileCombo.setCurrentText("boom")
        win.cellPanel.addFromTargetBtn.click()
        seededCell = list(win.cellPanel._cells.values())[0]
        win.cellPanel.cellList.setCurrentRow(0)

        orchestrator = win.orchestrator
        assert orchestrator is not None

        with pytest.raises(AbortExperiment):
            orchestrator.run_sync_cell(seededCell)

        # Both halves of the surfacing actually populated -- otherwise the
        # refcounting proof below would be proving nothing about them.
        assert win.statusPanel.lastError().exc_type == "RuntimeError"
        assert win.cellPanel.errorText(seededCell)[1] == "protocol blew up"
        # And still no per-entry bookkeeping held onto the entry itself.
        assert win.cellPanel._entryTimelineLoc == {}
        assert win.cellPanel._timelineItems == {}

        orchestrator_ref = weakref.ref(orchestrator)
        cell_ref = weakref.ref(seededCell)
        window_ref = weakref.ref(win)
        statusPanel_ref = weakref.ref(win.statusPanel)
        cellPanel_ref = weakref.ref(win.cellPanel)

        win.teardown()
        assert win.statusPanel._orchestrator is None
        assert win.cellPanel._orchestrator is None

        del orchestrator, seededCell
        win.close()
        del win
        # _processCell's logger.exception() call for this failure hands the
        # *live* RuntimeError to every handler on the root logger -- and
        # pytest attaches at least two of its own for the duration of a
        # test's call phase (one backing the caplog fixture, one private to
        # its terminal reporter, used to render the "Captured log call"
        # section). Either one's stored LogRecord keeps exc_info's traceback
        # alive, which keeps every frame it passed through -- and every local
        # bound in them, including this orchestrator -- reachable. That is
        # pytest's own bookkeeping for a report this test does not care
        # about, not anything the window's teardown owns, so every handler's
        # retained records are dropped here rather than left to prove
        # something about a reference this proof is not about.
        for handler in logging.getLogger().handlers:
            if hasattr(handler, "records"):
                handler.records.clear()
        # No gc.collect() -- pure refcounting only, since gc is disabled.

        assert orchestrator_ref() is None, "orchestrator should be freed by refcounting alone"
        assert cell_ref() is None, "seeded cell should be freed by refcounting alone"
        assert window_ref() is None, "window should be freed by refcounting alone"
        assert statusPanel_ref() is None, "StatusPanel should be freed by refcounting alone"
        assert cellPanel_ref() is None, "CellPanel should be freed by refcounting alone"
    finally:
        gc.enable()


def test_teardown_disconnects_every_cell_position_connection(qapp, tmp_path):
    """Qt's own receivers() count, not merely that an object was collectable:
    P2c-3a found a mandated mutation that did not fail because a nearby
    `= None` had already broken the cycle refcounting could see.

    Two cells, not one: a single connected cell cannot distinguish
    "disconnects every connection" from "disconnects at least one" -- a
    mutation that severed only the first cell it iterated over would still
    pass a one-cell version of this test.
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    from .test_window_integration import _makeCellAt

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    first = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    second = _makeCellAt(1.4e-3, 2.1e-3, -30e-6)
    win.cellPanel.addCell(first)
    win.cellPanel.addCell(second)
    assert first.receivers(first.sigPositionChanged) == 1
    assert second.receivers(second.sigPositionChanged) == 1

    win.teardown()

    assert first.receivers(first.sigPositionChanged) == 0
    assert second.receivers(second.sigPositionChanged) == 0
    assert win._positionConnected == {}
    assert win._cellPositions == {}

    win.close()


def test_teardown_releases_the_progress_overlay(qapp, tmp_path):
    """Qt's own receivers() count, not merely that an object was collectable:
    P2c-3a found a mandated mutation that did not fail because a nearby
    `= None` had already broken the cycle refcounting could see (see the
    cell-position test above). ProgressOverlay.release() disconnects
    scatter.sigClicked from the overlay's own _onScatterClicked -- a
    self-connection that is exactly that kind of reference cycle -- and takes
    the scatter back out of Area 1's view."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    scatter = win._progressOverlay.scatter
    assert scatter.receivers(scatter.sigClicked) == 1
    assert scatter in win.regionPanel.view.addedItems

    win.teardown()

    assert scatter.receivers(scatter.sigClicked) == 0
    assert scatter not in win.regionPanel.view.addedItems

    win.close()


def test_teardown_releases_the_reference_imagery(qapp, tmp_path):
    """ReferenceImagery.rebind() subscribes to the Camera module's
    ImagingCtrl, same as PinnedFrameMirror does -- a live connection there
    would go on recomputing Area 3's imagery instruction for a torn-down
    window. The manager and camera stand-ins come from test_window_integration
    for the same reason test_teardown_frees_the_slice_producer_and_cells_by_
    refcounting above borrows them: newSlice() needs a real camera and a real
    pinned-frame source to reach ReferenceImagery.beginSlice() at all.
    """
    from types import SimpleNamespace

    import acq4.util.DataManager as dm
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    from .test_window_integration import _FakeCameraWithDevice, _FakeManager

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    storageRoot = dm.getDirHandle(str(tmp_path / "storage"), create=True)

    win = AutopatchWindow(
        module=SimpleNamespace(manager=_FakeManager(storageRoot)),
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraWithDevice(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")

    win.newSlice()
    source = win.manager.pinnedFrameSource
    # Two, not merely nonzero: PinnedFrameMirror and ReferenceImagery both
    # subscribe to this signal, so pinning the precondition to just one of
    # them (> 0) would still be satisfied by PinnedFrameMirror alone even if
    # ReferenceImagery.rebind() never subscribed at all.
    assert source.receivers(source.sigPinnedFramesChanged) == 2

    win.teardown()

    assert source.receivers(source.sigPinnedFramesChanged) == 0

    win.close()
