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
