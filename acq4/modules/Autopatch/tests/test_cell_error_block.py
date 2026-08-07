"""Tests for Area 5's error block: a failed action's traceback, stored per cell
so it survives a selection change, and dropped when that cell starts a new pass."""
import gc
import weakref

import pytest

from acq4.experiment.exceptions import BrokenPipette
from acq4.experiment.log_entry import ActionLogEntry
from acq4.modules.Autopatch.error_display import ErrorBlock
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def panel(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel()


class _FakeOrchestrator(Qt.QObject):
    sigCurrentCell = Qt.Signal(object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)


def _finish_with_error(panel, cell, name="Patch", message="tip sheared off"):
    """Drive one action for `cell` all the way to a failed finish, the way a
    real run does: the panel wires the entry's callbacks in onLogAction()."""
    entry = ActionLogEntry(name)
    panel.onLogAction(cell, entry)
    try:
        raise BrokenPipette(message)
    except BrokenPipette as exc:
        entry._finish(exc)
    return entry


def _mounted_blocks(panel):
    layout = panel.showContainer.layout()
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), ErrorBlock)
    ]


def test_failed_action_mounts_an_error_block_for_the_selected_cell(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    blocks = _mounted_blocks(panel)
    assert len(blocks) == 1
    assert blocks[0].headlineLabel.text() == "BrokenPipette: tip sheared off"
    assert "BrokenPipette: tip sheared off" in blocks[0].tracebackView.toPlainText()


def test_error_block_survives_switching_cells_and_back(panel):
    # showContainer is cleared on every selection change, so a block mounted
    # only at finish time would be gone for good the first time the operator
    # looks at another cell.
    first, second = object(), object()
    panel.addCell(first)
    panel.addCell(second)
    panel.cellList.setCurrentItem(panel._rows[id(first)])
    _finish_with_error(panel, first)
    panel.cellList.setCurrentItem(panel._rows[id(second)])
    assert _mounted_blocks(panel) == []
    panel.cellList.setCurrentItem(panel._rows[id(first)])
    blocks = _mounted_blocks(panel)
    assert len(blocks) == 1
    assert blocks[0].headlineLabel.text() == "BrokenPipette: tip sheared off"


def test_successful_action_mounts_no_error_block(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(None)
    assert _mounted_blocks(panel) == []
    assert panel.errorText(cell) is None


def test_a_new_pass_clears_the_cells_stored_error(panel):
    # A cell that failed, was reused, and then ran again must not still be
    # showing the previous pass's traceback.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    assert panel.errorText(cell) is not None
    panel._onCurrentCell(cell)
    assert panel.errorText(cell) is None
    assert _mounted_blocks(panel) == []


def test_a_later_failure_supersedes_the_earlier_one(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell, name="Patch", message="first failure")
    _finish_with_error(panel, cell, name="Clean", message="second failure")
    exc_type, message, _tb = panel.errorText(cell)
    assert (exc_type, message) == ("BrokenPipette", "second failure")
    assert len(_mounted_blocks(panel)) == 1


def test_error_block_is_not_mounted_for_an_unselected_cell(panel):
    first, second = object(), object()
    panel.addCell(first)
    panel.addCell(second)
    panel.cellList.setCurrentItem(panel._rows[id(second)])
    _finish_with_error(panel, first)
    assert _mounted_blocks(panel) == []
    assert panel.errorText(first) is not None


def test_clear_cells_drops_the_error_store(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    panel.clearCells()
    assert panel.errorText(cell) is None
    assert _mounted_blocks(panel) == []


def test_discarding_a_cell_drops_its_stored_error(panel):
    # A rescan removing an unattempted row must not leave its traceback behind,
    # keyed by an id() that a future object could reuse.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    assert panel.isAttempted(cell) is False
    panel._onCellsDiscarded([cell])
    assert panel.errorText(cell) is None


def test_reuse_drops_the_cells_stored_error(panel):
    # A re-queued cell's previous traceback describes a pass that is over. Left
    # in _cellErrors, _onCellSelectionChanged would resurrect it beside a row
    # that now reads "queued" and a timeline that reuse has just emptied.
    cell, other = object(), object()
    panel.addCell(cell)
    panel.addCell(other)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    panel._onCellFinished(cell, "error")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    # Switch away and back -- the path _onCellSelectionChanged drives, which
    # is what re-mounts a block from whatever _cellErrors still holds.
    panel.cellList.setCurrentItem(panel._rows[id(other)])
    panel.cellList.setCurrentItem(panel._rows[id(cell)])

    assert _mounted_blocks(panel) == []
    assert panel.errorText(cell) is None


def test_panel_keeps_no_reference_to_the_failed_entry(panel):
    # An entry's on_finish closes over this panel; a panel holding the entry
    # back would form a cycle only the cyclic GC could break. See
    # tests/test_teardown.py for why this module must not have any.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    entry = _finish_with_error(panel, cell)
    ref = weakref.ref(entry)
    del entry
    gc.disable()
    try:
        assert ref() is None, "CellPanel is keeping the failed entry alive"
    finally:
        gc.enable()
    assert panel.errorText(cell) is not None
