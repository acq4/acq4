"""Tests for CellPanel: a manually-seeded cell queue (via "Add from target" and
"Scatter fake cells") kept in sync with the Orchestrator's per-cell signals."""
import gc
import threading
import weakref

import numpy as np
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentCell = Qt.Signal(object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)

    def pendingCells(self):
        """Stands in for Orchestrator.pendingCells(): this fake has no run
        loop to pop a cell off, so every cell .enqueue() has ever seen is
        still pending as far as a test using it is concerned."""
        return list(self.enqueued)


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


class _FakeCamera:
    def __init__(self, center):
        self._center = center

    def globalCenterPosition(self):
        return self._center


class _FakeQObjectCell(Qt.QObject):
    """Stands in for a real Cell (also a QObject): built on a worker thread the
    way tile_detector.py's _newCell constructs one from
    Orchestrator._refillQueue, so it does not live on the GUI thread
    addCell() runs on."""


def _buildOnAnotherThread(factory):
    result = {}

    def build():
        result["obj"] = factory()

    t = threading.Thread(target=build)
    t.start()
    t.join()
    return result["obj"]


def test_add_from_target_enqueues_and_lists(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.addFromTargetBtn.click()

    assert len(orch.enqueued) == 1
    cell = orch.enqueued[0]
    assert np.asarray(cell.position) == pytest.approx((1e-3, 2e-3, 3e-3))
    assert panel.cellList.count() == 1
    assert "queued" in panel.cellList.item(0).text()


def test_add_from_target_reads_position_via_patchpipette_manipulator(qapp):
    """"Add from target" must read the current target through the
    PatchPipette's manipulator (pipetteDevice.targetPosition()) -- a real
    PatchPipette has no targetPosition() of its own; only its .pipetteDevice
    (the underlying Pipette manipulator) exposes one."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((4e-3, 5e-3, 6e-3))
    assert not hasattr(pip, "targetPosition")
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.addFromTargetBtn.click()

    cell = orch.enqueued[0]
    assert np.asarray(cell.position) == pytest.approx((4e-3, 5e-3, 6e-3))


def test_add_from_target_is_a_noop_without_a_selected_pipette(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()  # no pipetteGetter injected -> resolves to None
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.addFromTargetBtn.click()

    assert orch.enqueued == []
    assert panel.cellList.count() == 0


def test_scatter_fake_cells_enqueues_a_handful_near_camera_center(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    cam = _FakeCamera((1e-3, 1e-3, 0.0))
    panel = CellPanel(cameraGetter=lambda: cam)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.scatterFakeCellsBtn.click()

    assert 3 <= len(orch.enqueued) <= 5
    assert panel.cellList.count() == len(orch.enqueued)
    center = np.array([1e-3, 1e-3, 0.0])
    for cell in orch.enqueued:
        offset = np.asarray(cell.position) - center
        assert np.all(np.abs(offset) < 100e-6)  # "near" the camera center


def test_scatter_fake_cells_is_a_noop_without_a_camera(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()  # no cameraGetter injected -> resolves to None
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.scatterFakeCellsBtn.click()

    assert orch.enqueued == []
    assert panel.cellList.count() == 0


def test_current_cell_updates_row_to_running(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((0, 0, 0))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]

    orch.sigCurrentCell.emit(cell)
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_add_from_target_without_an_orchestrator_bound_does_not_raise(qapp):
    """Seeding a cell before a protocol is loaded (no orchestrator bound yet)
    must not raise, and the cell must still show up in the list."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)

    panel.addFromTargetBtn.click()

    assert panel.cellList.count() == 1
    assert "queued" in panel.cellList.item(0).text()


def test_bind_orchestrator_flushes_previously_held_cells_exactly_once(qapp):
    """Cells seeded while no orchestrator was bound are flushed into the
    orchestrator bound afterward, each exactly once; a cell added after
    binding is enqueued exactly once too (no double-enqueue either way)."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)

    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    assert panel.cellList.count() == 2
    seededCells = list(panel._cells.values())

    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    assert len(orch.enqueued) == 2
    for cell in seededCells:
        assert orch.enqueued.count(cell) == 1

    panel.addFromTargetBtn.click()
    assert panel.cellList.count() == 3
    assert len(orch.enqueued) == 3
    newCell = orch.enqueued[-1]
    assert orch.enqueued.count(newCell) == 1


def test_a_cell_known_only_from_an_announcement_is_not_flushed_into_a_later_orchestrator(
    qapp,
):
    """A cell this panel only ever learned about from an orchestrator's
    announcements is already queued or already finished somewhere else, so
    binding a second orchestrator must not hand it over -- unlike a cell that
    is genuinely still sitting unrun in the outgoing orchestrator's own queue,
    which unbindOrchestrator() does carry over (see
    test_a_cell_seeded_while_bound_is_flushed_into_a_replacement_orchestrator).
    Both must hold at once, or "flush everything the first orchestrator ever
    saw" would pass this too.
    """
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)

    # Seeded with no orchestrator bound: this one is genuinely pending.
    panel.addFromTargetBtn.click()
    seededCell = list(panel._cells.values())[0]

    first = _FakeOrchestrator()
    panel.bindOrchestrator(first)
    assert first.enqueued == [seededCell]

    # And a cell the first orchestrator merely announces -- a survey producer's
    # find, enqueued inside the orchestrator itself.
    announced = object()
    first.sigCurrentCell.emit(announced)
    assert panel.cellList.count() == 2

    second = _FakeOrchestrator()
    panel.bindOrchestrator(second)

    assert second.enqueued == [
        seededCell
    ], "an announced cell was flushed into a rebind"


def test_a_finished_cell_is_not_flushed_into_a_later_orchestrator(qapp):
    """The "New slice" hazard, at panel level. newSlice() clears Area 5 and the
    orchestrator's queue but deliberately leaves the in-flight cell running; it
    finishes on the old tissue and is announced here. Loading a second protocol
    must not then enqueue that coordinate into the new orchestrator -- the
    operator has declared the tissue it names gone, and a pipette driven there
    is driven into whatever is now under the objective.
    """
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    first = _FakeOrchestrator()
    panel.bindOrchestrator(first)
    inFlight = object()
    first.sigCurrentCell.emit(inFlight)

    # The operator presses New slice: Area 5 and the queue are discarded while
    # that cell keeps running.
    panel.clearCells()
    first.sigCellFinished.emit(inFlight, "done")

    second = _FakeOrchestrator()
    panel.bindOrchestrator(second)

    assert second.enqueued == [], "a cell from discarded tissue was re-queued"


def test_a_finished_survey_is_not_flushed_into_a_later_orchestrator(qapp):
    """After a completed survey every produced cell has a row here. Loading a
    second protocol must enqueue none of them: they have already been patched,
    and running them again would patch each one a second time."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    first = _FakeOrchestrator()
    panel.bindOrchestrator(first)

    surveyed = [object() for _ in range(4)]
    for cell in surveyed:
        first.sigCurrentCell.emit(cell)
        first.sigCellFinished.emit(cell, "done")
    assert panel.cellList.count() == len(surveyed)

    second = _FakeOrchestrator()
    panel.bindOrchestrator(second)

    assert second.enqueued == []
    # The rows are still there -- the survey's record is not what gets dropped.
    assert panel.cellList.count() == len(surveyed)


def test_a_cell_seeded_while_bound_is_flushed_into_a_replacement_orchestrator(qapp):
    """A cell seeded with an orchestrator already bound is enqueued straight
    into that orchestrator's own queue, not into _awaitingEnqueue -- so if
    that orchestrator is replaced (a different protocol loaded) before the
    cell ever runs, unbindOrchestrator() must read it back out of the
    outgoing queue itself, or the cell's row would survive in Area 5 while
    the replacement orchestrator's queue holds nothing for it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)
    first = _FakeOrchestrator()
    panel.bindOrchestrator(first)

    panel.addFromTargetBtn.click()
    assert len(first.enqueued) == 1
    cell = first.enqueued[0]

    second = _FakeOrchestrator()
    panel.bindOrchestrator(second)

    assert second.enqueued == [cell]


def test_clear_cells_drops_the_pending_enqueue_bookkeeping(qapp):
    """clearCells() is the "these coordinates are gone" path, so a cell seeded
    before any orchestrator existed must not be flushed into one bound after
    the clear."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)
    panel.addFromTargetBtn.click()

    panel.clearCells()
    assert panel._awaitingEnqueue == []

    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    assert orch.enqueued == []


def test_cell_finished_updates_row(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((0, 0, 0))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]

    orch.sigCellFinished.emit(cell, "done")
    assert "done" in panel.cellList.item(0).text()


def test_rebinding_disconnects_previous_orchestrators_signals(qapp):
    """unbindOrchestrator() must disconnect exactly what bindOrchestrator()
    connected (sigCurrentCell, sigCellFinished), so a signal emitted by an
    orchestrator this panel is no longer bound to is silently ignored."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((0, 0, 0))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch1 = _FakeOrchestrator()
    orch2 = _FakeOrchestrator()
    panel.bindOrchestrator(orch1)
    panel.addFromTargetBtn.click()
    cell = orch1.enqueued[0]
    panel.bindOrchestrator(orch2)

    orch1.sigCurrentCell.emit(cell)
    orch1.sigCellFinished.emit(cell, "done")

    assert panel.cellList.item(0).text() == f"cell {id(cell)} — queued"


def test_rebinding_the_orchestrator_already_held_does_not_double_enqueue(qapp):
    """bindOrchestrator() called with the orchestrator it already holds is
    unreachable today -- the window that owns this panel always constructs a
    fresh Orchestrator when a protocol loads -- but unbindOrchestrator() now
    salvages the outgoing orchestrator's pending cells without clearing its
    queue, so a same-orchestrator rebind would otherwise flush those same
    still-queued cells into it a second time."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((1e-3, 2e-3, 3e-3))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.addFromTargetBtn.click()
    assert len(orch.enqueued) == 1
    cell = orch.enqueued[0]

    panel.bindOrchestrator(orch)

    assert orch.enqueued == [
        cell
    ], "re-binding the orchestrator already held re-queued its pending cell"


def test_current_cell_for_an_unseeded_cell_gets_exactly_one_running_row(qapp):
    """A cell the orchestrator announces via sigCurrentCell without ever having
    been seeded through addFromTargetBtn/scatterFakeCellsBtn (i.e. a cell a
    survey producer found and enqueued directly inside the orchestrator) must
    still get a row -- and that row must read "running", not "queued", since
    sigCurrentCell only ever fires for a cell about to run."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCurrentCell.emit(cell)

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_cell_finished_for_an_unseeded_cell_gets_a_row_with_its_status(qapp):
    """A cell can finish (e.g. Orchestrator's "skipped" outcome) without
    sigCurrentCell ever having fired for it, so _onCellFinished must add a row
    on its own rather than assuming _onCurrentCell already did."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCellFinished.emit(cell, "skipped")

    assert panel.cellList.count() == 1
    assert "skipped" in panel.cellList.item(0).text()


def test_current_cell_announced_twice_produces_exactly_one_row(qapp):
    """A retrying cell (or one simply re-announced as current) must not gain a
    second row -- self._rows is how _onCurrentCell tells it already has one."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCurrentCell.emit(cell)
    orch.sigCurrentCell.emit(cell)

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_seeded_cell_announced_as_current_does_not_duplicate_its_row(qapp):
    """A cell already seeded by hand (and so already holding a row from
    addCell()) must not get a second row when the orchestrator later announces
    it as current -- only its existing row's text should change."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    pip = _FakePipette((0, 0, 0))
    panel = CellPanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    assert panel.cellList.count() == 1

    orch.sigCurrentCell.emit(cell)

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_announced_cell_is_not_enqueued_into_the_bound_orchestrator(qapp):
    """A cell the panel only learns about via sigCurrentCell/sigCellFinished is
    already queued or running inside the orchestrator -- adding a display row
    for it must never also call orchestrator.enqueue(), which would patch the
    same cell a second time."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCurrentCell.emit(cell)
    orch.sigCellFinished.emit(cell, "done")

    assert orch.enqueued == []


def test_announced_cell_row_is_selectable_with_a_usable_timeline_and_log(qapp):
    """The whole point of giving an announced cell a row is that the operator
    can select it and see its timeline/log -- prove the row is genuinely
    usable (not just present) by selecting it and exercising the
    setdefault-based log/timeline paths against it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCurrentCell.emit(cell)
    panel.cellList.setCurrentRow(0)

    assert panel.cellList.currentItem().data(Qt.Qt.UserRole) is cell
    assert id(cell) in panel._timelines
    assert id(cell) in panel._logs

    panel.appendLog(cell, "hello from a surveyed cell")
    assert "hello from a surveyed cell" in panel.logView.toPlainText()


def test_clear_cells_resets_shown_entry_id_and_clears_show_container(qapp):
    """clearCells() is also CellPanel's rebind path (a freshly loaded protocol
    calls it before binding the new orchestrator, with the panel itself still
    alive), so a mounted details widget left over from the previous protocol
    must not survive it, and _shownEntryId must go back to None -- otherwise a
    recycled id(entry) after reload could match the stale value and cause a
    spurious container clear.

    This sets up the stale state directly (bypassing cellList selection)
    since clearCells() emptying an already-populated, currently-selected
    cellList would incidentally reset both via the ordinary
    currentItemChanged -> _onCellSelectionChanged path, masking whether
    clearCells() itself does the resetting."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    staleWidget = Qt.QLabel("stale details widget")
    panel.showContainer.layout().addWidget(staleWidget)
    panel._shownEntryId = 12345

    panel.clearCells()

    assert panel._shownEntryId is None
    assert panel.showContainer.layout().count() == 0


def test_current_cell_built_on_another_thread_gets_a_row_without_a_qt_warning(qapp):
    """A cell a survey producer finds runs through tile_detector.py's _newCell
    on the orchestrator's worker thread, so by the time sigCurrentCell carries
    it here (on the GUI thread), it is a QObject that does not live on this
    thread. Qt refuses setParent() across threads -- a stderr warning, not an
    exception -- so addCell() must recognize this case and skip the parenting
    rather than let that warning through; self._cells is what keeps such a
    cell alive instead, for as long as this panel exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = _buildOnAnotherThread(_FakeQObjectCell)
    assert cell.thread() is not panel.thread()

    messages = []
    Qt.qInstallMessageHandler(
        lambda msgType, context, message: messages.append(message)
    )
    try:
        orch.sigCurrentCell.emit(cell)
    finally:
        Qt.qInstallMessageHandler(None)

    assert messages == [], f"unexpected Qt warning(s): {messages}"
    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"
    assert cell.parent() is None


def test_current_cell_built_on_another_thread_is_still_freed_by_refcounting(qapp):
    """Since a cross-thread cell is never parented (see the test above),
    self._cells -- not Qt's ownership cascade -- must be what keeps it alive;
    prove that reference is also what lets it go, the same way
    tests/test_teardown.py proves for the same-thread case."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = _buildOnAnotherThread(_FakeQObjectCell)

    gc.disable()
    try:
        orch.sigCurrentCell.emit(cell)
        assert panel.cellList.count() == 1

        panel_ref = weakref.ref(panel)
        cell_ref = weakref.ref(cell)

        panel.clearCells()
        assert panel._cells == {}

        del cell, orch
        del panel
        # No gc.collect() below -- pure refcounting only, since gc is disabled.

        assert (
            cell_ref() is None
        ), "cross-thread cell should be freed by refcounting alone"
        assert panel_ref() is None, "panel should be freed by refcounting alone"
    finally:
        gc.enable()


def test_a_queued_cell_is_not_attempted(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    assert panel.isAttempted(cell) is False


def test_a_running_cell_is_attempted(qapp):
    """A cell interrupted mid-run may never emit a terminal status, so
    starting work on it -- not finishing -- is what marks it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCurrentCell(cell)

    assert panel.isAttempted(cell) is True


def test_a_finished_cell_is_attempted(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, "done")

    assert panel.isAttempted(cell) is True


def test_a_cell_finished_without_ever_being_current_is_attempted(qapp):
    """Orchestrator._processCell can emit "skipped" without sigCurrentCell
    ever firing for that cell."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()

    panel._onCellFinished(cell, "skipped")

    assert panel.isAttempted(cell) is True


def test_a_none_current_cell_does_not_crash_or_mark_anything(qapp):
    """_onCurrentCell(None) must be a genuine no-op: no crash, no row added
    for it, and no disturbance to a real cell already marked attempted --
    not just a check against isAttempted(None), which is False by default for
    any argument and so can never fail."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCurrentCell(cell)

    panel._onCurrentCell(None)

    assert panel.isAttempted(cell) is True
    assert panel.cellList.count() == 1


def test_discard_cells_removes_rows_for_cells_never_attempted(qapp):
    """A rescan discards whatever is still queued when the tissue moved; their
    rows in Area 5 must go with them, or an operator told "your N queued
    cells are discarded" still sees them listed as queued."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    discarded = object()
    panel.addCell(discarded)
    kept = object()
    panel.addCell(kept)

    panel.discardCells([discarded])

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).data(Qt.Qt.UserRole) is kept
    assert id(discarded) not in panel._cells
    assert id(discarded) not in panel._rows
    assert id(discarded) not in panel._timelines
    assert id(discarded) not in panel._logs


def test_discard_cells_never_removes_an_attempted_cells_row(qapp):
    """An attempted cell's row is the session record. discardCells() must
    never drop it, even when it is passed in directly -- e.g. a retried cell
    still sitting in the queue when the tissue moved."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    attempted = object()
    panel.addCell(attempted)
    panel._onCurrentCell(attempted)

    panel.discardCells([attempted])

    assert panel.cellList.count() == 1
    assert id(attempted) in panel._cells
    assert panel.isAttempted(attempted) is True


def test_discard_cells_drops_the_awaiting_enqueue_bookkeeping(qapp):
    """A discarded cell seeded before any orchestrator was bound must not be
    flushed into one bound afterward -- the same hazard clearCells() exists
    to avoid."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._awaitingEnqueue.append(id(cell))

    panel.discardCells([cell])

    assert panel._awaitingEnqueue == []


def test_clear_cells_forgets_the_attempted_set(qapp):
    """Left behind, a stale id would report a brand-new cell at a reused
    memory address as already attempted -- the same hazard _awaitingEnqueue
    is cleared for."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")

    panel.clearCells()

    assert panel.isAttempted(cell) is False


@pytest.mark.parametrize("status", ["done", "skipped", "stopped", "retry-exhausted", "error"])
def test_a_terminal_disposition_is_recorded(qapp, status):
    """Every status Orchestrator.sigCellFinished reports as terminal must be
    retrievable afterward: it is what "check all completed" and the reuse
    operation select on."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, status)

    assert panel.disposition(cell) == status


def test_a_never_run_cell_has_no_disposition(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    assert panel.disposition(cell) is None


def test_the_transient_retry_status_is_not_recorded_as_a_disposition(qapp):
    """"retry" is emitted mid-flight (Orchestrator._processCell) and is
    superseded by whatever terminal status the cell eventually reaches.
    Recorded as a disposition it would survive an interrupted run and read as
    though the cell had finished in a state named "retry"."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, "retry")

    assert panel.disposition(cell) is None


def test_a_retry_does_not_erase_an_earlier_terminal_disposition(qapp):
    """A cell reused for a second pass keeps its pass-1 disposition until the
    new pass reports its own terminal one; a transient "retry" in between must
    not blank it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")

    panel._onCellFinished(cell, "retry")

    assert panel.disposition(cell) == "done"


def test_a_later_terminal_disposition_replaces_an_earlier_one(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "error")

    panel._onCellFinished(cell, "done")

    assert panel.disposition(cell) == "done"


def test_clear_cells_forgets_recorded_dispositions(qapp):
    """Left behind, a stale id would report a brand-new cell at a reused memory
    address as already completed, offering it up to "check all completed" --
    the same hazard _awaitingEnqueue and _attempted are cleared for."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")

    panel.clearCells()

    assert panel.disposition(cell) is None


def test_discard_cells_forgets_a_discarded_cells_disposition(qapp):
    """discardCells() drops the same per-cell stores clearCells() drops, scoped
    to a subset; a disposition left behind is the same stale-id hazard."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    # Recorded directly rather than through _onCellFinished: that marks the
    # cell attempted, and discardCells() never touches an attempted cell.
    panel._status[id(cell)] = "done"

    panel.discardCells([cell])

    assert panel.disposition(cell) is None


def test_a_new_row_has_a_checkbox_and_starts_unchecked(qapp):
    """The checkbox is how an operator picks a reuse set; a row that starts
    checked would offer up cells nobody selected.

    checkState() alone cannot prove a checkbox is drawn: Qt reports
    Unchecked both for a row with an explicit unchecked state and for one
    with no check state at all, and only the former gets a checkbox. Assert
    CheckStateRole data is present -- that is what makes Qt draw the
    checkbox -- alongside checkState() to confirm it starts unchecked."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    panel.addCell(object())

    item = panel.cellList.item(0)
    assert item.data(Qt.Qt.CheckStateRole) is not None
    assert item.checkState() == Qt.Qt.Unchecked


def test_checking_a_row_does_not_change_the_inspected_cell(qapp):
    """Checking for reuse and selecting for inspection are independent
    gestures, so an operator can read one cell's log while a different set is
    checked (spec 6.1)."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    inspected = object()
    other = object()
    panel.addCell(inspected)
    panel.addCell(other)
    panel.cellList.setCurrentItem(panel._rows[id(inspected)])

    panel._rows[id(other)].setCheckState(Qt.Qt.Checked)

    assert panel.cellList.currentItem() is panel._rows[id(inspected)]
    assert panel._rows[id(inspected)].checkState() == Qt.Qt.Unchecked


def test_a_rows_check_state_survives_a_status_update(qapp):
    """_onCellFinished/_onCurrentCell call setText() on the same item; that must
    not disturb a check the operator has already made."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel._onCellFinished(cell, "done")

    assert panel._rows[id(cell)].checkState() == Qt.Qt.Checked
