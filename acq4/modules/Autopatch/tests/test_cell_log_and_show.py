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
    panel.appendLog("hello world")

    assert "hello world" in panel.logView.toPlainText()


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
