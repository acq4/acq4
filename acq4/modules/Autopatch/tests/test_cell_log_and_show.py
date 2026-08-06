"""Tests for CellPanel's log view (ctx.log sink) and the live details widget
mounted from a ctx.log_action() entry's set_details_widget(), both scoped to
the currently-followed (selected) cell."""
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


def test_append_log_shows_in_log_view(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentRow(0)

    panel.appendLog(cell, "hello world")

    assert "hello world" in panel.logView.toPlainText()


def test_log_is_scoped_to_the_selected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cellA, cellB = object(), object()
    panel.addCell(cellA)
    panel.addCell(cellB)
    panel.cellList.setCurrentRow(0)  # follow cellA

    panel.appendLog(cellA, "log line for A")
    panel.appendLog(cellB, "log line for B")

    assert "log line for A" in panel.logView.toPlainText()
    assert "log line for B" not in panel.logView.toPlainText()

    panel.cellList.setCurrentRow(1)  # switch to cellB

    assert "log line for B" in panel.logView.toPlainText()
    assert "log line for A" not in panel.logView.toPlainText()


def test_details_widget_mounted_for_selected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, action_entry)
    # Built on the GUI thread here, matching set_details_widget()'s requirement
    # that a widget handed to the UI must not be constructed off-thread.
    liveWidget = Qt.QLabel("live plot")
    action_entry.set_details_widget(liveWidget)

    assert panel.showContainer.layout().indexOf(liveWidget) != -1


def test_details_widget_not_mounted_for_unselected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    cellA, cellB = orch.enqueued
    panel.cellList.setCurrentRow(0)  # follow cellA

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cellB, action_entry)  # B is running, but A is selected
    liveWidget = Qt.QLabel("live plot for B")
    action_entry.set_details_widget(liveWidget)

    assert panel.showContainer.layout().indexOf(liveWidget) == -1


def test_details_widget_cleared_when_selection_moves_away_from_running_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    cellA, cellB = orch.enqueued
    panel.cellList.setCurrentRow(0)  # follow cellA

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cellA, action_entry)
    liveWidget = Qt.QLabel("live plot for A")
    action_entry.set_details_widget(liveWidget)
    assert panel.showContainer.layout().indexOf(liveWidget) != -1

    panel.cellList.setCurrentRow(1)  # switch away to cellB; cellA is still "running"

    assert panel.showContainer.layout().count() == 0


def test_finishing_an_entry_does_not_clear_another_entrys_still_mounted_widget(qapp):
    """If the currently mounted details widget belongs to a different, still
    in-flight entry than the one that just finished, finishing must not tear
    it down. No action currently nests log_action blocks, so this only
    happens if two entries are opened for the same cell in sequence and the
    earlier one outlives the later one's mount -- but the guard must hold
    regardless."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    outerEntry = ActionLogEntry("Outer")
    panel.onLogAction(cell, outerEntry)
    innerEntry = ActionLogEntry("Inner")
    panel.onLogAction(cell, innerEntry)

    innerWidget = Qt.QLabel("inner widget")
    innerEntry.set_details_widget(innerWidget)
    assert panel.showContainer.layout().indexOf(innerWidget) != -1

    outerEntry._finish(None)  # outer finishes; inner's widget is the live one

    assert panel.showContainer.layout().indexOf(innerWidget) != -1


def test_details_widget_cleared_when_the_entry_finishes(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, action_entry)
    liveWidget = Qt.QLabel("live plot")
    action_entry.set_details_widget(liveWidget)
    assert panel.showContainer.layout().indexOf(liveWidget) != -1

    action_entry._finish(None)

    assert panel.showContainer.layout().count() == 0
