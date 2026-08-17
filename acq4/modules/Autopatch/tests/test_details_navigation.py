"""Tests for CellPanel's retention of ActionLogEntry.set_details() payloads and
the timeline-row navigation that mounts them in the detail pane."""
import pytest

from acq4.experiment.log_entry import ActionLogEntry
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
        return []


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakePipette:
    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)


@pytest.fixture
def panel(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))


def _seed(panel, count=1):
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    for _ in range(count):
        panel.addFromTargetBtn.click()
    return orch.enqueued


def test_payload_is_retained_against_the_entrys_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["saved"]})


def test_payload_survives_the_entry_finishing(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})
    entry._finish(None)

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["saved"]})


def test_payloads_are_retained_per_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    first = ActionLogEntry("First")
    panel.onLogAction(cell, first)
    first.set_details("text", {"lines": ["one"]})
    first._finish(None)

    second = ActionLogEntry("Second")
    panel.onLogAction(cell, second)
    second.set_details("text", {"lines": ["two"]})
    second._finish(None)

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["one"]})
    assert panel.detailsFor(cell, 1) == ("text", {"lines": ["two"]})


def test_payloads_are_retained_for_an_unselected_cell(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(0)  # follow cellA while cellB works

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cellB, entry)
    entry.set_details("text", {"lines": ["B's stack"]})

    assert panel.detailsFor(cellB, 0) == ("text", {"lines": ["B's stack"]})


def test_clear_cells_drops_retained_payloads(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})

    panel.clearCells()

    assert panel._details == {}


def test_discarding_an_unattempted_cell_drops_its_payloads(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(0)
    entryA = ActionLogEntry("A")
    panel.onLogAction(cellA, entryA)
    entryA.set_details("text", {"lines": ["A"]})
    entryB = ActionLogEntry("B")
    panel.onLogAction(cellB, entryB)
    entryB.set_details("text", {"lines": ["B"]})

    panel._onCellsDiscarded([cellA])

    assert panel.detailsFor(cellA, 0) is None
    assert panel.detailsFor(cellB, 0) == ("text", {"lines": ["B"]})


def test_reuse_clears_the_cells_payloads(panel):
    # Pass 2 starts with a fresh timeline and log; retained details are that
    # same earlier-pass UI history and must go with them.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["pass 1"]})
    entry._finish(None)
    panel._onCellFinished(cell, "done")

    panel.cellList.item(0).setCheckState(Qt.Qt.Checked)
    panel.reuseCheckedCellsBtn.click()

    assert panel.detailsFor(cell, 0) is None
