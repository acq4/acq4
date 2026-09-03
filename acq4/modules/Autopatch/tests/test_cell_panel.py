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


def makePanel(**kwargs):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel(**kwargs)


class _FakeOrchestrator(Qt.QObject):
    sigCurrentCell = Qt.Signal(object)
    sigCellFinished = Qt.Signal(object, str)
    sigCellsQueued = Qt.Signal(object)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)

    def announceQueued(self, cells):
        """Stands in for the real orchestrator announcing the batch a survey
        producer just added to its queue -- which _refillQueue does *instead of*
        going through enqueue(), so nothing here records these as enqueued
        either."""
        self.sigCellsQueued.emit(list(cells))

    def announceCurrentCell(self, cell):
        """Stands in for the real orchestrator announcing the cell it has taken
        off the queue and started processing."""
        self.sigCurrentCell.emit(cell)

    def pendingCells(self):
        """Stands in for Orchestrator.pendingCells(): this fake has no run
        loop to pop a cell off, so every cell .enqueue() has ever seen is
        still pending as far as a test using it is concerned."""
        return list(self.enqueued)

    def clearQueue(self):
        """Stands in for Orchestrator.clearQueue(), which AutopatchWindow.
        newSlice() calls alongside CellPanel.clearCells(): the deque is a
        second strong reference to the same cells, and dropping it is what
        guarantees a merely-queued cell is never announced again."""
        self.enqueued.clear()


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
    first.announceCurrentCell(inFlight)

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


def test_current_cell_for_an_already_seeded_cell_announces_a_state_change(qapp):
    """The ordinary case -- a cell that already has a row, whether seeded by
    hand or announced once before -- must still tell Area 1's progress
    overlay to redraw when the orchestrator starts work on it. addCell()'s
    own emit (inside _onCurrentCell's "no row yet" branch, exercised by the
    test above) only ever fires for a cell with no row, so it cannot be what
    this case relies on; _onCurrentCell must emit sigCellStateChanged itself.

    panel.isAttempted(cell) must already read True by the time the signal
    fires: a consumer (AutopatchWindow._onCellStateChanged) re-reads it from
    inside its slot, the same ordering contract the sigCellStateChanged tests
    near the bottom of this file pin for addCell()/_onCellFinished()/
    _onCellsDiscarded()/_onReuseCheckedCells()."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    attemptedAtEmit = []
    panel.sigCellStateChanged.connect(lambda: attemptedAtEmit.append(panel.isAttempted(cell)))

    orch.sigCurrentCell.emit(cell)

    assert attemptedAtEmit == [True]


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


def test_a_wipe_after_reuse_frees_the_still_queued_cells(qapp):
    """Reuse re-queues the same Cell objects, so both the panel's stores and the
    orchestrator's deque hold each one, and a reused cell's tracker and reference
    image stack are exactly what makes retaining one costly. The wipe's two calls
    together have to let go of every cell still waiting its turn."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    # Built off-thread so addCell() leaves them unparented (see addCell()'s own
    # comment): the panel's own stores are then the only thing keeping them
    # alive, which is what gives the weakrefs below anything to prove.
    running, queuedFirst, queuedSecond = (
        _buildOnAnotherThread(_FakeQObjectCell) for _ in range(3)
    )
    for cell in (running, queuedFirst, queuedSecond):
        panel.addCell(cell)
        orch.sigCellFinished.emit(cell, "done")
    # The loop variable would otherwise be a reference of its own.
    del cell
    panel.checkAllCompletedBtn.click()
    panel.reuseCheckedCellsBtn.click()
    assert orch.enqueued == [running, queuedFirst, queuedSecond]
    # Pass 2 reaches the first of them; the other two are still queued behind it.
    orch.announceCurrentCell(running)
    refs = [weakref.ref(queuedFirst), weakref.ref(queuedSecond)]

    gc.disable()
    try:
        # What newSlice() does: the panel's bookkeeping and the orchestrator's
        # separate deque both let go.
        panel.clearCells()
        orch.clearQueue()

        del queuedFirst, queuedSecond
        # No gc.collect() -- pure refcounting, since gc is disabled.
        assert [ref() for ref in refs] == [
            None,
            None,
        ], "a cell that will never be announced again was pinned"
    finally:
        gc.enable()


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


def test_check_all_completed_checks_only_done_rows(qapp):
    """COMPLETED holds "done" alone. Every other terminal disposition is a
    manual opt-in, and "skipped" most of all: its name invites being read as a
    completion when it means the protocol abandoned the cell."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cells = {}
    for status in ("done", "skipped", "stopped", "retry-exhausted", "error"):
        cell = object()
        cells[status] = cell
        panel.addCell(cell)
        panel._onCellFinished(cell, status)
    neverRun = object()
    panel.addCell(neverRun)

    panel.checkAllCompletedBtn.click()

    assert panel._rows[id(cells["done"])].checkState() == Qt.Qt.Checked
    for status in ("skipped", "stopped", "retry-exhausted", "error"):
        assert panel._rows[id(cells[status])].checkState() == Qt.Qt.Unchecked, status
    assert panel._rows[id(neverRun)].checkState() == Qt.Qt.Unchecked


def test_check_all_completed_leaves_an_already_checked_row_checked(qapp):
    """The button only ever checks, never unchecks, so it composes with a
    selection the operator has already started making by hand.

    The hand-checked row here is deliberately *not* a completed one: a "done"
    row is one the button would tick anyway, so it would stay checked even
    under an implementation that unchecked everything first -- which would wipe
    exactly the manual selection this contract protects."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    byHand, completed = object(), object()
    panel.addCell(byHand)
    panel.addCell(completed)
    panel._onCellFinished(byHand, "error")
    panel._onCellFinished(completed, "done")
    panel._rows[id(byHand)].setCheckState(Qt.Qt.Checked)

    panel.checkAllCompletedBtn.click()

    assert panel._rows[id(byHand)].checkState() == Qt.Qt.Checked
    assert panel._rows[id(completed)].checkState() == Qt.Qt.Checked


def test_check_all_completed_is_disabled_with_nothing_completed(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "error")

    assert not panel.checkAllCompletedBtn.isEnabled()


def test_check_all_completed_enables_once_a_cell_completes(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, "done")

    assert panel.checkAllCompletedBtn.isEnabled()


def test_check_all_completed_disables_again_once_the_panel_is_cleared(qapp):
    """The button must not stay enabled over a selection that no longer exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    assert panel.checkAllCompletedBtn.isEnabled()

    panel.clearCells()

    assert not panel.checkAllCompletedBtn.isEnabled()


def test_reuse_enqueues_the_same_cell_objects_in_list_order(qapp):
    """Reuse re-queues the *same* Cell objects, which is what carries each
    cell's tracker/reference stack into the next pass (design doc 6)."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    first, second, skipMe = object(), object(), object()
    for cell in (first, skipMe, second):
        panel.addCell(cell)
        panel._onCellFinished(cell, "done")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(first)].setCheckState(Qt.Qt.Checked)
    panel._rows[id(second)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [first, second]


def test_reuse_resets_the_row_to_queued_and_clears_its_history(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._timelines[id(cell)] = ["patch — ✓ done (1.00s)"]
    panel._logs[id(cell)] = ["pass 1 log line"]
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel._rows[id(cell)].text() == f"cell {id(cell)} — queued"
    assert panel._timelines[id(cell)] == []
    assert panel._logs[id(cell)] == []
    assert panel.disposition(cell) is None
    assert panel._rows[id(cell)].checkState() == Qt.Qt.Unchecked


def test_reuse_keeps_the_cell_attempted(qapp):
    """isAttempted() is Slice.forceRescan's predicate and discardCells()' skip
    rule: it means work has started here at some point, which reuse does not
    undo. Cleared, a reused cell would be silently dropped from Area 5 by the
    next rescan and removed from the density record."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel.isAttempted(cell) is True


def test_reuse_never_re_enqueues_a_cell_that_has_not_finished_a_pass(qapp):
    """Nothing stops an operator checking a still-queued row. That cell is
    already in the orchestrator's queue, so enqueuing it again would run it
    twice against the same tissue."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    queued, finished = object(), object()
    panel.addCell(queued)
    panel.addCell(finished)
    panel._onCellFinished(finished, "done")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(queued)].setCheckState(Qt.Qt.Checked)
    panel._rows[id(finished)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [finished]
    assert panel._rows[id(queued)].text() == f"cell {id(queued)} — queued"
    assert panel._rows[id(queued)].checkState() == Qt.Qt.Unchecked


def test_reuse_leaves_unchecked_cells_alone(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    reused, untouched = object(), object()
    for cell in (reused, untouched):
        panel.addCell(cell)
        panel._onCellFinished(cell, "done")
    panel._logs[id(untouched)] = ["keep me"]
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(reused)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [reused]
    assert panel.disposition(untouched) == "done"
    assert panel._logs[id(untouched)] == ["keep me"]
    assert panel._rows[id(untouched)].text() == f"cell {id(untouched)} — done"


def test_reuse_clears_the_detail_views_of_the_inspected_cell(qapp):
    """Spec 8: stale pass-1 timeline/log content must not linger in the pane
    for a cell that is now queued for pass 2 -- nor a details widget a pass-1
    action mounted in the show container, and nor the _shownEntryId naming it,
    whose stale value a recycled id(entry) in pass 2 could match and cause a
    spurious container clear.

    The mounted widget and _shownEntryId are set up after the row is selected:
    selecting it runs _onCellSelectionChanged, which resets both, so priming
    them earlier would prove nothing about what reuse itself does."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._timelines[id(cell)] = ["patch — ✓ done (1.00s)"]
    panel._logs[id(cell)] = ["pass 1 log line"]
    panel._onCellFinished(cell, "done")
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    assert panel.timelineList.count() == 1
    panel.showContainer.layout().addWidget(Qt.QLabel("pass 1 details widget"))
    panel._shownEntryId = 12345
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel.timelineList.count() == 0
    assert panel.logView.toPlainText() == ""
    assert panel.showContainer.layout().count() == 0
    assert panel._shownEntryId is None


def test_reuse_disables_check_all_completed_once_the_last_one_is_reused(qapp):
    """Reuse pops the disposition it re-queues on, so the button that selects on
    those dispositions must be re-evaluated: left enabled, it would offer a
    selection that no longer exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    assert panel.checkAllCompletedBtn.isEnabled()

    panel.reuseCheckedCellsBtn.click()

    assert not panel.checkAllCompletedBtn.isEnabled()


def test_reuse_is_disabled_without_an_orchestrator(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_with_nothing_checked(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_enabled_once_bound_idle_and_checked(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())

    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    assert panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_while_a_run_is_in_flight(qapp):
    """"Start nothing new" at action boundaries, and never re-queue a cell the
    orchestrator may be working on right now."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.setInteractionLocked(True)

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_re_enables_when_the_run_unlocks(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    panel.setInteractionLocked(True)

    panel.setInteractionLocked(False)

    assert panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_once_the_last_checked_row_is_discarded(qapp):
    """A rescan takes rows away with takeItem(), which emits no itemChanged --
    so nothing else re-evaluates the gate, and the button would stay enabled
    over a selection that no longer exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._status[id(cell)] = "done"
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    assert panel.reuseCheckedCellsBtn.isEnabled()

    panel.discardCells([cell])

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_again_after_unbinding(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    assert panel.reuseCheckedCellsBtn.isEnabled()

    panel.unbindOrchestrator()

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_discarding_a_reused_pending_cell_restores_its_pre_reuse_disposition(qapp):
    """A rescan discards every pending cell, reused ones included -- but reuse
    deliberately keeps a cell attempted, so discardCells() skips its row. Left
    as reuse wrote it, that row would read "queued" while no queue holds the
    cell: unreachable by Start, by reuse, and by "Check all completed" alike,
    and still in the density record so the survey cannot re-find it either.
    Restored to the disposition it held before reuse, the row is a session
    record again and the operator can knowingly reuse it once they trust the
    new coordinates.
    """
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    running, pending = object(), object()
    for cell in (running, pending):
        panel.addCell(cell)
        panel._onCellFinished(cell, "done")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(running)].setCheckState(Qt.Qt.Checked)
    panel._rows[id(pending)].setCheckState(Qt.Qt.Checked)
    panel.reuseCheckedCellsBtn.click()
    assert orch.enqueued == [running, pending]
    # Pass 2 starts: the first cell runs, the second is still queued behind it
    # when tracking loses the first and the operator answers "Rescan".
    panel._onCurrentCell(running)
    assert panel.disposition(pending) is None

    panel.discardCells([pending])

    assert panel.cellList.count() == 2, "a reused cell's row was dropped"
    assert panel.disposition(pending) == "done"
    assert panel._rows[id(pending)].text() == f"cell {id(pending)} — done"
    assert panel.checkAllCompletedBtn.isEnabled()
    panel.checkAllCompletedBtn.click()
    assert panel._rows[id(pending)].checkState() == Qt.Qt.Checked


def test_discarding_a_never_reused_attempted_cell_leaves_its_row_alone(qapp):
    """Only a cell reuse actually took a disposition from gets one back: an
    attempted cell that never went through reuse has nothing to restore, and
    its row must keep saying whatever it said."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCurrentCell(cell)

    panel.discardCells([cell])

    assert panel.disposition(cell) is None
    assert panel._rows[id(cell)].text() == f"cell {id(cell)} — running"


def test_a_reused_cell_that_finishes_pass_2_keeps_no_pre_reuse_disposition(qapp):
    """The remembered value must not outlive the pass it was remembered for: a
    cell that finished pass 2 in error and is then discarded must read "error",
    not the "done" it earned a pass ago."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    panel.reuseCheckedCellsBtn.click()

    panel._onCellFinished(cell, "error")

    assert panel._preReuseStatus == {}
    panel.discardCells([cell])
    assert panel.disposition(cell) == "error"


def test_clear_cells_forgets_a_remembered_pre_reuse_disposition(qapp):
    """Left behind, a stale id would hand a brand-new cell at a reused memory
    address a disposition it never earned -- the same hazard _awaitingEnqueue,
    _attempted and _status are cleared for."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    panel.reuseCheckedCellsBtn.click()
    assert panel._preReuseStatus != {}

    panel.clearCells()

    assert panel._preReuseStatus == {}


def test_cells_reports_every_cell_the_panel_knows(qapp):
    panel = makePanel()
    first, second = object(), object()

    panel.addCell(first)
    panel.addCell(second)

    assert panel.cells() == [first, second]


def test_cells_includes_a_hand_added_cell_absent_from_any_slice(qapp):
    """The overlay reads this, not Slice._cells, because registerCells() has
    one production caller and hand-added cells never reach it. Reading the
    slice instead would silently omit every "Add from target" cell.
    """
    panel = makePanel()
    handAdded = object()

    panel.addCell(handAdded)

    assert handAdded in panel.cells()


def test_adding_a_cell_announces_a_state_change(qapp):
    """A consumer reacting to sigCellStateChanged re-reads panel.cells() from
    inside its slot, so the cell must already be in that list by emit time.
    Kills a mutation that moves addCell()'s emit to the very start of the
    method, before the cell is recorded in self._cells."""
    panel = makePanel()
    cell = object()
    snapshots = []
    panel.sigCellStateChanged.connect(lambda: snapshots.append(panel.cells()))

    panel.addCell(cell)

    assert cell in snapshots[0]


def test_a_finished_cell_announces_a_state_change(qapp):
    """A consumer reacting to sigCellStateChanged re-reads
    panel.disposition(cell) from inside its slot, so the disposition must
    already be terminal by emit time. Kills a mutation that moves
    _onCellFinished()'s emit before self._status[id(cell)] is set."""
    panel = makePanel()
    cell = object()
    panel.addCell(cell)
    dispositions = []
    panel.sigCellStateChanged.connect(lambda: dispositions.append(panel.disposition(cell)))

    panel._onCellFinished(cell, "done")

    assert dispositions == ["done"]


def test_discarding_a_cell_announces_it_after_the_row_is_gone(qapp):
    """Pins the ordering a later consumer depends on: by the time
    sigCellStateChanged fires for a discard, panel.cells() must already
    exclude the discarded cell (while still including any other cell), or a
    consumer reconciling from inside its slot would report a cell that is no
    longer here. Kills a mutation that moves _onCellsDiscarded()'s emit
    before the rows are removed."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    discarded, kept = object(), object()
    panel.addCell(discarded)
    panel.addCell(kept)
    snapshots = []
    panel.sigCellStateChanged.connect(lambda: snapshots.append(panel.cells()))

    panel.discardCells([discarded])

    assert snapshots == [[kept]]


def test_reusing_a_checked_cell_announces_a_state_change(qapp):
    """A consumer reacting to sigCellStateChanged re-reads
    panel.disposition(cell) from inside its slot, so a reused cell's
    disposition must already read as re-queued (None), not its old terminal
    value, by emit time."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    dispositions = []
    panel.sigCellStateChanged.connect(lambda: dispositions.append(panel.disposition(cell)))

    panel.reuseCheckedCellsBtn.click()

    assert dispositions == [None]


def test_select_cell_makes_that_row_current(qapp):
    """selectCell must follow its argument and not just select the last row."""
    panel = makePanel()
    first, second, third = object(), object(), object()
    panel.addCell(first)
    panel.addCell(second)
    panel.addCell(third)

    # Make third the current row first (it's also the last-added)
    panel.selectCell(third)

    # Now select first, which is neither last-added nor currently-selected
    panel.selectCell(first)

    assert panel.cellList.currentItem().data(Qt.Qt.UserRole) is first


def test_select_cell_ignores_a_cell_with_no_row(qapp):
    """Area 1 can report a click for a cell the panel has already discarded.

    Two halves, both required: a stale click must not raise out of a Qt slot,
    and it must not silently move the operator's current selection either.
    """
    panel = makePanel()
    known = object()
    panel.addCell(known)
    panel.selectCell(known)

    panel.selectCell(object())

    assert panel.cellList.currentItem().data(Qt.Qt.UserRole) is known


def test_zoom_button_requests_the_selected_cell(qapp):
    panel = makePanel()
    cell = object()
    panel.addCell(cell)
    panel.selectCell(cell)
    seen = []
    panel.sigZoomToCellRequested.connect(seen.append)

    panel.zoomToCellBtn.click()

    assert seen == [cell]


def test_zoom_button_does_nothing_with_no_selection(qapp):
    panel = makePanel()
    seen = []
    panel.sigZoomToCellRequested.connect(seen.append)

    panel.zoomToCellBtn.click()

    assert seen == []


# ---- the whole discovered queue, not just the cell in hand ----
#
# A survey finds a queue's worth of cells at a time, on the orchestrator's
# worker thread, with nothing in this panel having seeded any of them. Before
# sigCellsQueued the only thing that ever said so was one of them starting to
# run, so the operator watched an empty list while cellpose worked through a
# tile and then saw a single "running" row appear with no sign of the rest.


def test_a_queued_batch_gets_rows_before_any_of_it_runs(qapp):
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cells = [object(), object()]

    orch.announceQueued(cells)

    assert panel.cellList.count() == 2
    for index, cell in enumerate(cells):
        assert panel.cellList.item(index).text() == f"cell {id(cell)} — queued"


def test_a_queued_batch_is_neither_enqueued_nor_left_awaiting_one(qapp):
    """These cells are already in the orchestrator's own deque -- that is what
    the announcement means. Enqueuing them here would run each twice, and
    recording them as awaiting an enqueue would have the next bindOrchestrator()
    do the same thing one protocol load later."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    orch.announceQueued([object(), object()])

    assert orch.enqueued == []
    assert panel._awaitingEnqueue == []
    later = _FakeOrchestrator()
    panel.bindOrchestrator(later)
    assert later.enqueued == []


def test_a_queued_cell_that_then_runs_keeps_its_one_row(qapp):
    """The same cell is announced twice -- once when the survey queues it and
    again when the orchestrator takes it in hand -- and must end with one row
    that has moved on from "queued", not a second row."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.announceQueued([cell])
    orch.announceCurrentCell(cell)

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_a_cell_that_already_has_a_row_is_not_reset_by_a_queue_announcement(qapp):
    """A cell can reach this panel by some other route first -- seeded by hand,
    or added by unbindOrchestrator() salvaging the outgoing orchestrator's
    pending queue -- and a later batch naming it must leave that row alone
    rather than giving it a second one or walking its text back to "queued"."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()
    orch.announceCurrentCell(cell)

    orch.announceQueued([cell])

    assert panel.cellList.count() == 1
    assert panel.cellList.item(0).text() == f"cell {id(cell)} — running"


def test_a_queued_batch_from_the_worker_thread_is_marshaled_onto_the_gui_thread(qapp):
    """The real emit comes from Orchestrator._refillQueue, on the worker thread,
    and a QListWidget must only ever be touched from the GUI thread. The
    connection this panel makes is signal-to-slot between two QObjects, so Qt's
    automatic connection is what marshals it -- which is only true if the rows
    appear when this thread pumps its event loop, and not one moment earlier."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cells = [object(), object()]

    thread = threading.Thread(target=lambda: orch.announceQueued(cells))
    thread.start()
    thread.join()

    assert panel.cellList.count() == 0, "the rows were added on the worker thread"
    qapp.processEvents()
    assert panel.cellList.count() == 2


def test_unbinding_stops_a_queue_announcement_from_reaching_the_list(qapp):
    """unbindOrchestrator() must disconnect sigCellsQueued along with the other
    two, or an orchestrator this panel has stopped tracking goes on filling
    Area 5 with cells from a run it is no longer showing."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.unbindOrchestrator()

    orch.announceQueued([object()])

    assert panel.cellList.count() == 0


# ---- following the cell the run is working on ----
#
# The cell-level counterpart of the timeline's auto-scroll rule (see
# _isFollowingLastRow): without it, a run announces its first cell and Area 5
# sits there with nothing selected -- no timeline, no log, an empty details
# pane -- until the operator clicks the one row on the list.


def test_the_announced_cell_takes_the_selection(qapp):
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.announceCurrentCell(cell)

    assert panel.cellList.currentItem() is panel._rows[id(cell)]


def test_each_announced_cell_takes_the_selection_from_the_last(qapp):
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    first, second = object(), object()

    orch.announceCurrentCell(first)
    orch.announceCurrentCell(second)

    assert panel.cellList.currentItem() is panel._rows[id(second)]


def test_a_cell_the_operator_selected_keeps_the_selection(qapp):
    """Once the operator goes back to read through a cell that is not the one
    running, the run stops taking the selection away from them."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    first, second, third = object(), object(), object()
    orch.announceCurrentCell(first)
    orch.announceCurrentCell(second)

    panel.selectCell(first)
    orch.announceCurrentCell(third)

    assert panel.cellList.currentItem() is panel._rows[id(first)]


def test_selecting_the_running_cell_again_resumes_following(qapp):
    """The way back: selecting whichever cell the run is on now is what says
    "carry on showing me the run", exactly as selecting the last timeline row
    resumes the auto-scroll one level down."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    first, second, third = object(), object(), object()
    orch.announceCurrentCell(first)
    # A queued cell of the operator's choosing, read back through while the run
    # carries on without them.
    panel.addCell(second)
    panel.selectCell(second)
    orch.announceCurrentCell(third)
    assert panel.cellList.currentItem() is panel._rows[id(second)]

    panel.selectCell(third)
    fourth = object()
    orch.announceCurrentCell(fourth)

    assert panel.cellList.currentItem() is panel._rows[id(fourth)]


def test_a_row_selected_before_the_run_started_is_not_taken_away(qapp):
    """A selection the operator made by hand with nothing announced yet is still
    a deliberate one: the first cell the run announces must not steal it."""
    pip = _FakePipette((0, 0, 0))
    panel = makePanel(pipetteGetter=lambda: pip)
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    seeded, other = orch.enqueued
    panel.selectCell(seeded)

    orch.announceCurrentCell(other)

    assert panel.cellList.currentItem() is panel._rows[id(seeded)]


def test_the_followed_cells_timeline_and_log_are_really_populated(qapp):
    """setCurrentItem, not a shortcut around it: the selection change is what
    fills the timeline and the log from this cell's stores, so a cell announced
    after it has already logged something shows that history without a click."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()
    panel.addCell(cell)
    panel.appendLog(cell, "before it was announced")
    qapp.processEvents()

    orch.announceCurrentCell(cell)

    assert "before it was announced" in panel.logView.toPlainText()


def test_clear_cells_forgets_which_cell_was_being_followed(qapp):
    """Ids are recycled: a cleared panel that still remembers the id of a cell
    it no longer holds could read a brand new cell's row as "where the panel
    last put the selection" purely because the two share an address."""
    panel = makePanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    orch.announceCurrentCell(object())

    panel.clearCells()

    assert panel._announcedCellId is None


# ---- how small the panel is willing to get ----
#
# Area 5 is a scrolling viewport over this panel (see AutopatchWindow._makeArea),
# so what the operator gets when they drag its handle up is decided here: a panel
# that insists on a tall minimum is a panel that goes behind scrollbars the
# moment the area is squeezed, taking the queue, the timeline and the buttons
# with it. Everything scrollable in here -- the two lists, the log, the details
# pane -- can show a few rows and scroll the rest instead, which is what these
# check.


def _rowsHigh(widget, rows):
    """The height `rows` rows of that widget's own text occupy."""
    return rows * widget.fontMetrics().height()


def _panelFloor(panel):
    """What this panel may insist on: a button row, and a dozen rows of text
    shared between the two lists, the status line, the details pane and the log.

    Rows of the panel's own font rather than a pixel count, so this says the
    same thing on a rig whose font is not this one's.
    """
    return panel.addFromTargetBtn.sizeHint().height() + _rowsHigh(panel, 12)


def test_the_panel_minimum_is_a_button_row_and_a_few_rows_of_text(qapp):
    panel = makePanel()

    assert panel.minimumSizeHint().height() <= _panelFloor(panel), (
        panel.minimumSizeHint().height(),
        _panelFloor(panel),
    )


def test_the_panel_still_asks_for_a_working_size(qapp):
    """The other half: a smaller minimum, not a smaller preference.

    AutopatchWindow._seedOpeningSplit divides each splitter in proportion to
    what the areas ask for, so a panel whose sizeHint collapsed onto its
    minimum would open the window with Area 5 as a sliver.

    Stated as headroom above the floor rather than as a multiple of it: the
    pinned cell queue puts four and a half rows into the floor whether the
    panel is squeezed or not (see _CELL_LIST_ROWS), and a ratio would read that
    as the preference having shrunk when it is the floor that rose.
    """
    panel = makePanel()

    headroom = panel.sizeHint().height() - panel.minimumSizeHint().height()
    assert headroom >= _rowsHigh(panel, 8), (headroom, _rowsHigh(panel, 8))


def test_a_mounted_details_widget_does_not_raise_the_panel_minimum(qapp):
    """A details widget is whatever the action that produced it wants to be --
    an ImageView, a test-pulse plot -- and several of them ask for a few hundred
    pixels. Mounting one must not hand that demand to the whole panel, or
    selecting a row with a figure in it would push the cell queue off screen.
    """
    panel = makePanel()
    insistent = Qt.QWidget()
    insistent.setMinimumSize(400, 400)

    panel.showContainer.layout().addWidget(insistent)
    qapp.processEvents()

    assert panel.minimumSizeHint().height() <= _panelFloor(panel), (
        panel.minimumSizeHint().height(),
        _panelFloor(panel),
    )


def test_a_long_status_does_not_stop_the_panel_narrowing(qapp):
    """statusLabel wraps, and a wrapping label ordinarily answers "how tall are
    you?" with "how wide are you making me?": the narrower the panel, the taller
    that one label. Worse, Qt has no minimum height-for-width across a widget
    boundary -- QWidgetItem answers minimumHeightForWidth() with plain
    heightForWidth() -- so one such label is enough to make this whole panel's
    minimum height equal its preferred height, and an area holding it can only
    scroll it. Driven the way an area does it: through a resizable viewport, at
    a width and a height that are both a squeeze.
    """
    panel = makePanel()
    panel.statusLabel.setText("waiting for the pipette to reach the cell " * 12)
    viewport = Qt.QScrollArea()
    viewport.setWidgetResizable(True)
    viewport.setWidget(panel)
    viewport.resize(260, _panelFloor(panel) + 20)
    viewport.show()
    try:
        for _ in range(3):
            qapp.processEvents()

        assert panel.height() <= viewport.viewport().height(), (
            panel.height(),
            viewport.viewport().height(),
        )
        assert not viewport.verticalScrollBar().isVisible()
        assert panel.statusLabel.height() <= _rowsHigh(panel.statusLabel, 3)
    finally:
        viewport.close()


def test_the_lists_still_show_rows_when_the_panel_is_at_its_minimum(qapp):
    """Small enough to be squeezed, big enough to be worth reading: at the
    panel's own minimum the queue and the timeline are still showing rows, and
    scrolling within themselves rather than pushing the panel taller.
    """
    panel = makePanel()
    for i in range(40):
        panel.addCell(object())
    panel.resize(panel.sizeHint().width(), panel.minimumSizeHint().height())
    panel.layout().activate()

    assert panel.cellList.height() >= _rowsHigh(panel.cellList, 4), (
        panel.cellList.height()
    )
    assert panel.timelineList.height() >= _rowsHigh(panel.timelineList, 3), (
        panel.timelineList.height()
    )
    assert panel.timelineList.height() <= _rowsHigh(panel.timelineList, 5), (
        panel.timelineList.height()
    )


def test_the_cell_queue_is_the_same_height_however_the_panel_is_sized(qapp):
    """The queue is what the operator reads to find their place, and it moved
    every time anything else in the panel did: cells arriving, the timeline
    filling, a details figure being mounted. It is pinned instead, and the
    room those things want comes out of the views that scroll.
    """
    panel = makePanel()
    panel.resize(panel.sizeHint().width(), panel.minimumSizeHint().height())
    panel.layout().activate()
    squeezed = panel.cellList.height()

    for i in range(40):
        panel.addCell(object())
    figure = Qt.QLabel("a details figure")
    figure.setMinimumSize(400, 400)
    panel.showContainer.layout().addWidget(figure)
    panel.resize(panel.sizeHint().width(), 4 * panel.sizeHint().height())
    panel.layout().activate()

    assert panel.cellList.height() == squeezed, (panel.cellList.height(), squeezed)


def test_the_cell_queue_shows_four_and_a_half_cells(qapp):
    """Four rows and the top of a fifth: enough of the queue to work in, and a
    cut-off row to say there is more of it below."""
    panel = makePanel()
    for i in range(40):
        panel.addCell(object())
    panel.resize(panel.sizeHint().width(), panel.sizeHint().height())
    panel.layout().activate()

    row = panel.cellList.sizeHintForRow(0)
    assert 4 * row < panel.cellList.height() < 5 * row, (
        panel.cellList.height(),
        row,
    )


def test_a_mounted_details_widget_is_given_room_to_show(qapp):
    """The other side of the details pane insisting on nothing: what it does
    ask for has to keep up with what is mounted in it.

    A QWidget caches the size it last reported to the layout above it, and
    filling a scroll area's content invalidates the layouts inside that content
    only -- so a pane left to that cache goes on offering the hint it computed
    while it was empty, and every figure an action produces is mounted into a
    strip a few pixels tall with its own scrollbars.
    """
    panel = makePanel()
    panel.resize(600, 700)
    panel.show()
    try:
        qapp.processEvents()
        figure = Qt.QLabel("a details figure")
        figure.setMinimumSize(400, 400)

        panel.showContainer.layout().addWidget(figure)
        # Two passes of the loop, because it takes two: the container's layout
        # request reaches the pane in the first, and the panel's own re-layout
        # is what the pane posts from there.
        qapp.processEvents()
        qapp.processEvents()

        assert panel.showViewport.height() >= 300, panel.showViewport.height()
        # And still the panel's own minimum, not the figure's: the pane grew
        # into room the panel had, and would give it back again.
        assert panel.minimumSizeHint().height() <= _panelFloor(panel)
    finally:
        panel.close()


# --- synthetic "Tracker initialized" row (the reference-stack backfill) ---
#
# A cell with an initialized tracker always has a reference stack
# (Cell.isInitialized reports self._tracker is not None), but nothing showed
# it anywhere -- most visibly after a reuse pass, which wipes a cell's
# timeline for its next pass while the tracker (and the reference stack it
# holds) lives on unchanged on the Cell object itself. These tests cover the
# synthetic row cell_panel.py seeds at index 0 of a cell's timeline to
# surface that stack through the existing details pane, with no new UI and
# no invented details kind.


def _cellWithReferenceStack(stack=None):
    """A real Cell (not a plain object()) with a stubbed-in tracker whose
    reference-stack chain matches the one cell_panel.py and
    acq4.experiment.actions.device._trackerStack both read:
    cell._tracker.motion_estimator.original_object_stack.data.

    A real Cell rather than a fake is used because isInitialized is a Cell
    property (self._tracker is not None), and stubbing a whole fake class
    just to reproduce that one property would be more code than reusing the
    real thing.
    """
    import types

    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    cell = Cell(Point((0.0, 0.0, 0.0), "global"))
    if stack is None:
        stack = np.arange(2 * 3 * 3, dtype=float).reshape(2, 3, 3)
    cell._tracker = types.SimpleNamespace(
        motion_estimator=types.SimpleNamespace(
            original_object_stack=types.SimpleNamespace(data=stack)
        )
    )
    return cell


def test_a_cell_with_an_initialized_tracker_gets_a_synthetic_reference_row(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    # A cellfie's own reference-stack payload transposes the last two axes
    # (see acq4.experiment.actions.device._trackerStack); an all-equal stack
    # sidesteps needing to reproduce that transform just to assert on it.
    stack = np.full((2, 3, 3), 7.0)
    cell = _cellWithReferenceStack(stack)

    panel.addCell(cell)

    assert panel._timelines[id(cell)] == ["Tracker initialized"]
    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "image_stack"
    assert np.array_equal(np.asarray(payload["stack"]), stack)


def test_a_cell_with_no_tracker_gets_no_synthetic_row(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel
    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    panel = CellPanel()
    cell = Cell(Point((0.0, 0.0, 0.0), "global"))  # _tracker is None -> not initialized
    assert cell.isInitialized is False

    panel.addCell(cell)

    assert panel._timelines[id(cell)] == []
    assert panel.detailsFor(cell, 0) is None


def test_real_actions_after_the_synthetic_row_land_at_index_one_with_no_reindexing(qapp):
    from acq4.experiment.log_entry import ActionLogEntry

    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = _cellWithReferenceStack()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])

    entry = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["pass 1"]})
    entry._finish(None)

    assert panel._timelines[id(cell)][0] == "Tracker initialized"
    assert "Pipette To Home" in panel._timelines[id(cell)][1]
    assert panel.detailsFor(cell, 0)[0] == "image_stack"
    assert panel.detailsFor(cell, 1) == ("text", {"lines": ["pass 1"]})


def test_after_a_reuse_pass_wipes_the_timeline_the_synthetic_row_reappears(qapp):
    """The backfill this feature exists for: reuse wipes the timeline (and
    self._details with it) while the cell's tracker -- and the reference
    stack cached from its first real image_stack detail -- live on.

    The cell has no tracker yet when addCell() runs (the common case for a
    manually-added cell, or one a survey found before cellfie ever ran on
    it), so the cache below can only have come from the real action's own
    set_details() call, over sigActionEntry -- not from addCell()'s own
    live-read fallback, which never had anything to read at that point.
    """
    from acq4.experiment.log_entry import ActionLogEntry
    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = Cell(Point((0.0, 0.0, 0.0), "global"))
    panel.addCell(cell)  # no tracker yet -> nothing cached, no synthetic row
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    # Cellfie is what actually initializes the tracker in production
    # (Cell.initializeTracker); a bare stand-in is enough here since this
    # test cares only about the cache _onActionEntry populates from the
    # entry's own set_details() payload below, not about a live tracker read.
    cell._tracker = object()
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details(
        "image_stack", {"stack": np.ones((2, 2, 2)), "center_index": 0, "title": "Cellfie"}
    )
    entry._finish(None)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel._timelines[id(cell)] == ["Tracker initialized"]
    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "image_stack"
    assert np.array_equal(payload["stack"], np.ones((2, 2, 2)))


def test_reuse_never_reads_the_tracker_directly_when_nothing_was_ever_cached(qapp):
    """The thread-safety guard: once a cell has been attempted, seeding the
    synthetic row must come only from a payload this panel already cached off
    sigActionEntry, never from a fresh read of cell._tracker -- reading that
    on the GUI thread once a pass may still have a worker-thread job appending
    to it (see 2794be759) is exactly the race this panel must not take. A cell
    that finished a pass without ever attaching an image_stack detail (no
    cache exists) must therefore get no synthetic row on reuse, even though
    its tracker is still sitting right there with a stack to read.

    The tracker is attached only after addCell() -- addCell() itself is a
    provably quiet moment this panel does allow a live read from (see
    _seedReferenceStackRow), and pre-seeding it before addCell() would let
    that live read cache a stack of its own, which is exactly the confound
    this test needs to avoid to isolate the "already attempted" guard.
    """
    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = Cell(Point((0.0, 0.0, 0.0), "global"))
    panel.addCell(cell)  # no tracker yet -> addCell()'s own live read finds nothing
    cell._tracker = object()  # now initialized, but no action ever cached its stack
    # First pass never attached an image_stack detail (e.g. every action
    # logged something else), so nothing was ever cached for this cell.
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel._timelines[id(cell)] == []
    assert panel.detailsFor(cell, 0) is None


def test_auto_select_row_does_not_select_the_synthetic_row_when_real_actions_exist(qapp):
    from acq4.experiment.log_entry import ActionLogEntry

    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = _cellWithReferenceStack()
    panel.addCell(cell)
    entry = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cell, entry)
    entry._finish(None)

    panel.cellList.setCurrentItem(panel._rows[id(cell)])

    assert panel.timelineList.count() == 2
    assert panel.timelineList.currentRow() == 1


def test_auto_select_row_picks_the_synthetic_row_when_it_is_the_only_one(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = _cellWithReferenceStack()
    panel.addCell(cell)

    panel.cellList.setCurrentItem(panel._rows[id(cell)])

    assert panel.timelineList.count() == 1
    assert panel.timelineList.currentRow() == 0


def test_selecting_the_synthetic_row_mounts_the_reference_stack_widget(qapp):
    import pyqtgraph as pg

    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = _cellWithReferenceStack(np.zeros((2, 3, 3)))
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])

    panel.timelineList.setCurrentRow(0)

    assert panel.showContainer.findChild(pg.ImageView) is not None
