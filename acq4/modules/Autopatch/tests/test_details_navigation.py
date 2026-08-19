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
    sigCellsQueued = Qt.Signal(object)

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


def _mounted(panel):
    layout = panel.showContainer.layout()
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def test_selecting_a_finished_row_mounts_its_payload(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["the cellfie stack"]})
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert len(_mounted(panel)) == 1
    assert "the cellfie stack" in _mounted(panel)[0].toPlainText()


def test_selecting_a_different_row_swaps_the_mounted_payload(panel):
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

    panel.timelineList.setCurrentRow(0)
    assert "one" in _mounted(panel)[0].toPlainText()

    panel.timelineList.setCurrentRow(1)
    assert "two" in _mounted(panel)[0].toPlainText()


def test_selecting_a_row_with_no_payload_leaves_the_pane_empty(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cell, entry)
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert _mounted(panel) == []


def test_a_live_widget_is_remounted_when_its_row_is_reselected(panel):
    # Navigating away clears the container, which reparents the live widget out.
    # Coming back must put the same widget back, not a dead one.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    finished = ActionLogEntry("Earlier")
    panel.onLogAction(cell, finished)
    finished._finish(None)

    live = ActionLogEntry("Patch")
    panel.onLogAction(cell, live)
    liveWidget = Qt.QLabel("live plot")
    live.set_details_widget(liveWidget)
    assert liveWidget in _mounted(panel)

    panel.timelineList.setCurrentRow(0)
    assert liveWidget not in _mounted(panel)

    panel.timelineList.setCurrentRow(1)
    assert liveWidget in _mounted(panel)


def test_a_finished_entrys_live_widget_is_forgotten(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_details_widget(Qt.QLabel("live plot"))
    entry._finish(None)

    assert panel._liveWidgets == {}


def test_a_payload_arriving_for_the_selected_row_mounts_immediately(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    panel.timelineList.setCurrentRow(0)

    entry.set_details("text", {"lines": ["just arrived"]})

    assert "just arrived" in _mounted(panel)[0].toPlainText()


def test_a_payload_replaces_the_live_widget_on_the_same_row(panel):
    # patch()'s finally sets its payload while its live plot is still mounted.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    liveWidget = Qt.QLabel("live plot")
    entry.set_details_widget(liveWidget)
    panel.timelineList.setCurrentRow(0)
    assert liveWidget in _mounted(panel)

    entry.set_details("text", {"lines": ["frozen"]})

    assert liveWidget not in _mounted(panel)
    assert "frozen" in _mounted(panel)[0].toPlainText()


def test_a_new_row_is_followed_while_the_last_row_is_selected(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    first = ActionLogEntry("First")
    panel.onLogAction(cell, first)
    first._finish(None)
    assert panel.timelineList.currentRow() == 0

    second = ActionLogEntry("Second")
    panel.onLogAction(cell, second)

    assert panel.timelineList.currentRow() == 1


def test_selecting_an_earlier_row_stops_following(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cell, entry)
        entry._finish(None)

    panel.timelineList.setCurrentRow(0)  # operator navigates back

    third = ActionLogEntry("Third")
    panel.onLogAction(cell, third)

    assert panel.timelineList.currentRow() == 0


def test_returning_to_the_last_row_resumes_following(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cell, entry)
        entry._finish(None)
    panel.timelineList.setCurrentRow(0)
    third = ActionLogEntry("Third")
    panel.onLogAction(cell, third)
    third._finish(None)
    assert panel.timelineList.currentRow() == 0

    panel.timelineList.setCurrentRow(panel.timelineList.count() - 1)

    fourth = ActionLogEntry("Fourth")
    panel.onLogAction(cell, fourth)

    assert panel.timelineList.currentRow() == panel.timelineList.count() - 1


def test_selecting_a_cell_auto_selects_its_running_row(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)  # look at B so A's rows build unrendered
    done = ActionLogEntry("Done")
    panel.onLogAction(cellA, done)
    done._finish(None)
    running = ActionLogEntry("Running")
    panel.onLogAction(cellA, running)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 1
    assert "running" in panel.timelineList.item(1).text()


def test_selecting_a_cell_auto_selects_its_failed_row(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)
    failed = ActionLogEntry("Patch")
    panel.onLogAction(cellA, failed)
    failed._finish(RuntimeError("boom"))
    later = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cellA, later)
    later._finish(None)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 0


def test_selecting_a_cell_auto_selects_the_last_row_when_nothing_stands_out(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cellA, entry)
        entry._finish(None)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 1


def test_selecting_a_cell_with_no_rows_selects_nothing(panel):
    cellA, cellB = _seed(panel, 2)
    entry = ActionLogEntry("First")
    panel.onLogAction(cellA, entry)
    entry._finish(None)
    panel.cellList.setCurrentRow(0)

    panel.cellList.setCurrentRow(1)

    assert panel.timelineList.currentRow() == -1
    assert _mounted(panel) == []


def test_a_failed_action_records_an_error_payload_on_its_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "error"
    assert payload["exc_type"] == "RuntimeError"
    assert payload["exc_message"] == "boom"
    assert "RuntimeError: boom" in payload["traceback_text"]
    assert payload["cell_repr"] == repr(cell)


def test_a_failed_actions_row_mounts_an_error_block(panel):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    panel.timelineList.setCurrentRow(0)

    assert isinstance(_mounted(panel)[0], ErrorBlock)


def test_a_failed_action_that_set_a_payload_keeps_the_payload(panel):
    # The data it gathered before dying beats the traceback, which the log and
    # the row's outcome glyph both still carry.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["got this far"]})
    entry._finish(RuntimeError("boom"))

    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "text"
    assert payload == {"lines": ["got this far"]}


def test_error_text_still_answers_which_cell_failed(panel):
    # _cellErrors and errorText() are a different question from "what did this
    # row do", and tests/test_teardown.py asserts against errorText.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    assert panel.errorText(cell)[0] == "RuntimeError"
    assert panel.errorText(cell)[1] == "boom"


def test_a_successful_action_records_no_error_payload(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(None)

    assert panel.detailsFor(cell, 0) is None


def test_status_shows_for_the_selected_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)

    entry.set_status("driving FSM from 'approach'")

    assert "driving FSM from 'approach'" in panel.statusLabel.text()


def test_status_updates_in_place_as_the_action_progresses(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)

    entry.set_status("now in 'seal'")
    entry.set_status("reached 'whole cell'")

    assert "reached 'whole cell'" in panel.statusLabel.text()
    assert "now in 'seal'" not in panel.statusLabel.text()


def test_status_is_not_shown_for_an_unselected_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    earlier = ActionLogEntry("Earlier")
    panel.onLogAction(cell, earlier)
    earlier.set_status("earlier status")
    earlier._finish(None)
    later = ActionLogEntry("Later")
    panel.onLogAction(cell, later)
    later.set_status("later status")

    panel.timelineList.setCurrentRow(0)

    assert "earlier status" in panel.statusLabel.text()
    assert "later status" not in panel.statusLabel.text()


def test_last_status_is_retained_after_the_action_finishes(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_status("saving cellfie z-stack")
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert "saving cellfie z-stack" in panel.statusLabel.text()


def test_status_clears_for_a_row_that_never_reported_one(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    withStatus = ActionLogEntry("With")
    panel.onLogAction(cell, withStatus)
    withStatus.set_status("something")
    withStatus._finish(None)
    withoutStatus = ActionLogEntry("Without")
    panel.onLogAction(cell, withoutStatus)
    withoutStatus._finish(None)

    panel.timelineList.setCurrentRow(1)

    assert panel.statusLabel.text() == ""


def test_clear_cells_drops_retained_statuses(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_status("something")

    panel.clearCells()

    assert panel._statuses == {}
    assert panel.statusLabel.text() == ""


# ---- what the operator sees on startup, before they touch anything ----
#
# No setCurrentRow, no click, nothing selected by hand anywhere below: the run
# announces a cell and the panel has to arrive at the row worth looking at on
# its own, or Area 5 opens blank and stays blank until someone clicks it.


def test_the_first_action_of_the_first_cell_shows_without_a_click(panel):
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()

    orch.sigCurrentCell.emit(cell)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_status("acquiring the cellfie stack")
    entry.set_details("text", {"lines": ["the cellfie stack"]})

    assert panel.cellList.currentItem() is not None
    assert panel.timelineList.currentRow() == 0
    assert panel.statusLabel.text() == "acquiring the cellfie stack"
    assert len(_mounted(panel)) == 1
    assert "the cellfie stack" in _mounted(panel)[0].toPlainText()


def test_the_pane_follows_each_action_of_the_followed_cell(panel):
    """_autoSelectRow picks the row worth looking at when a cell is selected;
    from there it is the timeline's own auto-scroll rule that keeps the pane on
    whichever action is running now, without either one being clicked."""
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    cell = object()
    orch.sigCurrentCell.emit(cell)

    first = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, first)
    first.set_details("text", {"lines": ["one"]})
    first._finish(None)
    second = ActionLogEntry("Patch")
    panel.onLogAction(cell, second)
    second.set_details("text", {"lines": ["two"]})

    assert panel.timelineList.currentRow() == 1
    assert "two" in _mounted(panel)[0].toPlainText()


def test_returning_to_the_working_cell_shows_the_action_it_is_on(panel):
    """The other way into _autoSelectRow's "the action still running" branch,
    and the one the operator reaches by hand: they wander off to another cell
    while the run works, then come back, and the pane lands on the action in
    flight rather than on the last one that finished."""
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    watched, working = object(), object()
    panel.addCell(working)
    panel.addCell(watched)
    panel.selectCell(watched)

    finished = ActionLogEntry("Cellfie")
    panel.onLogAction(working, finished)
    finished.set_details("text", {"lines": ["done with this"]})
    finished._finish(None)
    running = ActionLogEntry("Patch")
    panel.onLogAction(working, running)
    running.set_details("text", {"lines": ["still going"]})

    panel.selectCell(working)

    assert panel.timelineList.currentRow() == 1
    assert "still going" in _mounted(panel)[0].toPlainText()
