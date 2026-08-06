"""Tests for CellPanel's per-cell executed-path timeline, built live from
ctx.log_action() entries delivered via CellPanel.onLogAction, cell-bound by
the context factory."""
import pytest

from acq4.experiment.log_entry import ActionLogEntry
from acq4.util import Qt
from acq4.util.task import Stopped


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentCell = Qt.Signal(object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []
        self._currentCell = None

    def enqueue(self, cell):
        self.enqueued.append(cell)

    def currentCell(self):
        """Stands in for Orchestrator.currentCell(): the cell being processed
        right now, or None when none is.

        Part of the interface CellPanel requires of whatever it is bound to --
        clearCells() asks it which cell a wipe must remember -- so the fake
        answers it even though no test here puts a cell in hand."""
        return self._currentCell


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


def test_timeline_appends_a_running_row_when_an_entry_starts(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, action_entry)

    assert panel.timelineList.count() == 1
    text = panel.timelineList.item(0).text()
    assert "Patch" in text
    assert "running" in text


def test_timeline_row_updates_in_place_when_the_entry_finishes(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    action_entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, action_entry)
    action_entry._finish(None)  # ctx.log_action()'s normal exit -> outcome "done"

    assert panel.timelineList.count() == 1  # updated in place, not appended
    text = panel.timelineList.item(0).text()
    assert "Patch" in text
    assert "done" in text
    assert "running" not in text


def test_timeline_row_glyph_matches_error_and_stopped_outcomes(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    panel.addFromTargetBtn.click()
    cellA, cellB = orch.enqueued

    panel.cellList.setCurrentRow(0)
    errorEntry = ActionLogEntry("Patch")
    panel.onLogAction(cellA, errorEntry)
    errorEntry._finish(RuntimeError("boom"))
    errorText = panel.timelineList.item(0).text()
    assert "error" in errorText
    assert "✗" in errorText
    assert "✓" not in errorText

    panel.cellList.setCurrentRow(1)
    stoppedEntry = ActionLogEntry("Patch")
    panel.onLogAction(cellB, stoppedEntry)
    stoppedEntry._finish(Stopped("operator stop"))
    stoppedText = panel.timelineList.item(0).text()
    assert "stopped" in stoppedText
    assert "⊘" in stoppedText
    assert "✓" not in stoppedText


def test_timeline_row_glyph_matches_abandoned_outcome(qapp):
    # A FlowSignal (e.g. AdvanceToNextCell from the operator's "Next cell" mid-
    # action) escaping an action's log_action block must render as abandoned,
    # not as a false "done" -- an action cut short did not complete.
    from acq4.modules.Autopatch.cell_panel import CellPanel
    from acq4.experiment.exceptions import AdvanceToNextCell

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    abandonedEntry = ActionLogEntry("Patch")
    panel.onLogAction(cell, abandonedEntry)
    abandonedEntry._finish(AdvanceToNextCell("advance to next cell"))
    abandonedText = panel.timelineList.item(0).text()
    assert "abandoned" in abandonedText
    assert "⊘" in abandonedText
    assert "✓" not in abandonedText
    assert "— ✓ done" not in abandonedText


def test_timeline_preserved_across_cell_switch(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cellA = orch.enqueued[0]
    panel.addFromTargetBtn.click()
    cellB = orch.enqueued[1]

    entryA = ActionLogEntry("Alpha")
    panel.onLogAction(cellA, entryA)
    entryA._finish(None)

    entryB = ActionLogEntry("Beta")
    panel.onLogAction(cellB, entryB)

    panel.cellList.setCurrentRow(0)
    linesA = [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())]
    assert len(linesA) == 1
    assert "Alpha" in linesA[0] and "done" in linesA[0]

    panel.cellList.setCurrentRow(1)
    linesB = [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())]
    assert len(linesB) == 1
    assert "Beta" in linesB[0] and "running" in linesB[0]


def test_non_selected_cells_rows_are_recorded_but_not_rendered(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cellA = orch.enqueued[0]
    panel.addFromTargetBtn.click()
    cellB = orch.enqueued[1]
    panel.cellList.setCurrentRow(0)  # follow cellA

    entryB = ActionLogEntry("Beta")
    panel.onLogAction(cellB, entryB)  # cellB is running, but cellA is selected

    assert panel.timelineList.count() == 0

    panel.cellList.setCurrentRow(1)  # switch to cellB: its recorded row replays
    assert panel.timelineList.count() == 1
    assert "Beta" in panel.timelineList.item(0).text()


def test_selecting_a_still_running_cell_resumes_live_updates(qapp):
    """A cell selected while its current entry is still in-flight must have its
    row update in place once that entry finishes, not just get a fresh row on
    the next onLogAction call."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cellA = orch.enqueued[0]
    panel.addFromTargetBtn.click()
    cellB = orch.enqueued[1]
    panel.cellList.setCurrentRow(0)  # follow cellA while cellB runs

    entryB = ActionLogEntry("Beta")
    panel.onLogAction(cellB, entryB)

    panel.cellList.setCurrentRow(1)  # switch to the still-running cellB
    assert panel.timelineList.count() == 1
    assert "running" in panel.timelineList.item(0).text()

    entryB._finish(None)

    assert panel.timelineList.count() == 1  # still updated in place
    assert "done" in panel.timelineList.item(0).text()


def test_log_action_entries_marshal_from_the_worker_thread_to_the_gui_thread(qapp, qtbot, tmp_path):
    """ctx.log_action() opens on the orchestrator's worker thread (a real
    gentletask ThreadTask launched by Orchestrator.start()), and
    CellPanel.onLogAction plus the entry's on_status/on_widget/on_finish
    callbacks all run there too -- see cell_panel.py's onLogAction docstring.
    Prove the timeline update genuinely lands on the GUI thread by comparing
    the QThread the protocol body executed on against the QThread
    CellPanel.sigActionEntry's connected slot executed on, rather than just
    checking that the values eventually arrive."""
    from acq4.experiment.orchestrator import Orchestrator
    from acq4.experiment.protocol_file import ProtocolFile
    from acq4.modules.Autopatch.cell_panel import CellPanel
    from acq4.modules.Autopatch.context_factory import make_context_factory

    protocol_path = tmp_path / "marshal_demo.py"
    protocol_path.write_text(
        "\"\"\"Test fixture protocol: opens one log_action and records the\n"
        "worker thread it ran on, onto the cell, for the test to inspect.\"\"\"\n"
        "from acq4.util import Qt\n\n\n"
        "def run(ctx, **kwargs):\n"
        "    with ctx.log_action('Patch') as action_entry:\n"
        "        ctx.cell._workerThread = Qt.QtCore.QThread.currentThread()\n"
    )
    pf = ProtocolFile(str(protocol_path))
    pf.load()

    panel = CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))

    guiThreads = []
    panel.sigActionEntry.connect(lambda *_: guiThreads.append(Qt.QtCore.QThread.currentThread()))

    factory = make_context_factory(
        pipetteGetter=lambda: None,
        manager=None,
        log=panel.appendLog,
        onLogAction=panel.onLogAction,
    )
    orch = Orchestrator(pf, contextFactory=factory)
    panel.bindOrchestrator(orch)
    panel.addFromTargetBtn.click()
    cell = list(panel._cells.values())[0]
    panel.cellList.setCurrentRow(0)  # follow the cell so its timeline row renders

    orch.start()
    qtbot.waitUntil(lambda: hasattr(cell, "_workerThread"), timeout=2000)
    qtbot.waitUntil(lambda: len(guiThreads) >= 2, timeout=2000)  # "started" and "finished"

    mainThread = Qt.QtCore.QThread.currentThread()
    assert all(t is mainThread for t in guiThreads)
    assert cell._workerThread is not mainThread
    # The marshaled entries must actually have driven CellPanel's own slot,
    # not just reached this test's separately-connected lambda.
    assert panel.timelineList.count() == 1
    assert panel.timelineList.item(0).text().startswith("Patch")
