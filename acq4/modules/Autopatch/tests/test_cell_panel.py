"""Tests for CellPanel: a manually-seeded cell queue (via "Add from target" and
"Scatter fake cells") kept in sync with the Orchestrator's per-cell signals."""
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
