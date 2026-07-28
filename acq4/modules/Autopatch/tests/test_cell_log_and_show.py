"""Tests for CellPanel's log view (ctx.log sink) and live show()-widget mount,
both scoped to the currently-followed (selected) cell."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentAction = Qt.Signal(object, object)
    sigCellFinished = Qt.Signal(object, str)
    sigActionFinished = Qt.Signal(object, object, str)

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


class _FakeAction(Qt.QObject):
    sigStateChanged = Qt.Signal(object, str)

    def __init__(self, name, widget=None):
        super().__init__()
        self.name = name
        self._widget = widget

    def show(self):
        return self._widget


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


def test_show_widget_mounted_for_selected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    liveWidget = Qt.QLabel("live plot")
    action = _FakeAction("Patch", widget=liveWidget)
    orch.sigCurrentAction.emit(cell, action)

    assert panel.showContainer.layout().indexOf(liveWidget) != -1


def test_show_widget_not_mounted_for_unselected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    cellA, cellB = orch.enqueued
    panel.cellList.setCurrentRow(0)  # follow cellA

    liveWidget = Qt.QLabel("live plot for B")
    action = _FakeAction("Patch", widget=liveWidget)
    orch.sigCurrentAction.emit(cellB, action)  # B is running, but A is selected

    assert panel.showContainer.layout().indexOf(liveWidget) == -1


def test_show_widget_cleared_when_selection_moves_away_from_running_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    cellA, cellB = orch.enqueued
    panel.cellList.setCurrentRow(0)  # follow cellA

    liveWidget = Qt.QLabel("live plot for A")
    action = _FakeAction("Patch", widget=liveWidget)
    orch.sigCurrentAction.emit(cellA, action)
    assert panel.showContainer.layout().indexOf(liveWidget) != -1

    panel.cellList.setCurrentRow(1)  # switch away to cellB; cellA is still "running"

    assert panel.showContainer.layout().count() == 0
