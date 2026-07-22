"""Tests for CellPanel's per-cell executed-path timeline, built live from
Orchestrator.sigActionFinished(cell, action, outcome) as it drives each cell."""
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


class _Action:
    name = "Patch"


def test_timeline_appends_a_line_per_action_finished(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]

    orch.sigActionFinished.emit(cell, _Action(), "reached 'whole cell'")
    orch.sigActionFinished.emit(cell, _Action(), "done")

    panel.cellList.setCurrentRow(0)
    lines = [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())]
    assert lines == [
        "Patch: reached 'whole cell'",
        "Patch: done",
    ]


def test_timeline_preserved_across_cell_switch(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cellA = orch.enqueued[0]
    panel.addFromTargetBtn.click()
    cellB = orch.enqueued[1]

    orch.sigActionFinished.emit(cellA, _Action(), "hello A")
    orch.sigActionFinished.emit(cellB, _Action(), "hello B")

    panel.cellList.setCurrentRow(0)
    assert [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())] == [
        "Patch: hello A"
    ]

    panel.cellList.setCurrentRow(1)
    assert [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())] == [
        "Patch: hello B"
    ]


def test_rebinding_disconnects_previous_orchestrator_action_finished(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch1 = _FakeOrchestrator()
    orch2 = _FakeOrchestrator()
    panel.bindOrchestrator(orch1)
    panel.addFromTargetBtn.click()
    cell = orch1.enqueued[0]
    panel.bindOrchestrator(orch2)

    orch1.sigActionFinished.emit(cell, _Action(), "should be ignored")

    panel.cellList.setCurrentRow(0)
    assert panel.timelineList.count() == 0
