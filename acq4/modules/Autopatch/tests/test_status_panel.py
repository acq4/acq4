"""Tests for StatusPanel: Start/Stop/Pause/Next wired to an Orchestrator, and
sigStatus / a cell-bound ctx.log_action() entry stream reflected in the status
and current-action labels."""
import pytest

from acq4.experiment.log_entry import ActionLogEntry
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)
    sigCurrentCell = Qt.Signal(object)
    sigRunError = Qt.Signal(object)

    def __init__(self):
        super().__init__()
        self.started = self.stopped = self.paused = self.resumed = self.nexted = 0
        self.stopReason = None

    def start(self):
        self.started += 1

    def stop(self, reason=""):
        self.stopped += 1
        self.stopReason = reason

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def requestNextCell(self):
        self.nexted += 1


class _FakeEntrySource(Qt.QObject):
    """Stands in for CellPanel: the only surface StatusPanel needs from it is
    the cell-bound sigActionEntry(cell, entry, phase) stream."""

    sigActionEntry = Qt.Signal(object, object, str)


def test_buttons_drive_the_bound_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    # Freshly bound (protocol loaded, not yet running): only Start is enabled.
    panel.startBtn.click()
    assert orch.started == 1

    # Once running, Stop/Pause/Next are enabled and each reaches the orchestrator.
    orch.sigStatus.emit("running")
    panel.pauseBtn.click()
    panel.stopBtn.click()
    panel.nextBtn.click()

    assert orch.paused == 1
    assert orch.stopped == 1
    assert orch.nexted == 1


def test_stop_button_passes_a_real_reason_not_the_click_signal_s_bool(qapp):
    # Qt's clicked signal carries a `checked` bool; connecting it straight to
    # orchestrator.stop would pass that bool through as `reason`, landing a
    # bogus `False` in the run log instead of a human-readable reason.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    panel.stopBtn.click()

    assert orch.stopped == 1
    assert isinstance(orch.stopReason, str) and orch.stopReason != ""
    assert orch.stopReason is not False


def test_pause_button_toggles_to_resume_while_paused(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    panel.pauseBtn.click()
    assert orch.paused == 1
    assert orch.resumed == 0

    orch.sigStatus.emit("paused")
    assert panel.pauseBtn.text() == "Resume"
    panel.pauseBtn.click()
    assert orch.resumed == 1


def test_status_signal_updates_label(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.show()  # isVisible() only reflects setVisible() once shown
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    assert "running" in panel.statusLabel.text().lower()

    orch.sigStatus.emit("error")
    assert "error" in panel.statusLabel.text().lower()


def test_current_action_entry_updates_label_with_name_and_status(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    class _Cell:
        def __repr__(self):
            return "cell-1"

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    entrySource = _FakeEntrySource()
    panel.bindOrchestrator(orch, entrySource)

    cell = _Cell()
    action_entry = ActionLogEntry("Patch")
    entrySource.sigActionEntry.emit(cell, action_entry, "started")
    assert "Patch" in panel.currentActionLabel.text()
    assert "cell-1" in panel.currentActionLabel.text()

    action_entry.set_status("seeking")
    entrySource.sigActionEntry.emit(cell, action_entry, "status")
    assert "seeking" in panel.currentActionLabel.text()

    orch.sigCurrentCell.emit(None)
    assert panel.currentActionLabel.text() == ""


def test_current_action_label_clears_on_transition_to_a_new_cell(qapp):
    """sigCurrentCell(cellB) fires directly after cellA (no None in between) when
    the orchestrator advances straight to the next cell; if cellB's protocol
    opens no log_action at all, the label must not keep showing cellA's last
    action instead of going blank for cellB."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    class _Cell:
        def __init__(self, label):
            self._label = label

        def __repr__(self):
            return self._label

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    entrySource = _FakeEntrySource()
    panel.bindOrchestrator(orch, entrySource)

    cellA = _Cell("cell-A")
    orch.sigCurrentCell.emit(cellA)
    action_entry = ActionLogEntry("Patch")
    entrySource.sigActionEntry.emit(cellA, action_entry, "started")
    assert "Patch" in panel.currentActionLabel.text()

    cellB = _Cell("cell-B")
    orch.sigCurrentCell.emit(cellB)  # advance directly to the next cell

    assert panel.currentActionLabel.text() == ""


def test_rebinding_disconnects_previous_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch1 = _FakeOrchestrator()
    orch2 = _FakeOrchestrator()
    panel.bindOrchestrator(orch1, _FakeEntrySource())
    panel.bindOrchestrator(orch2, _FakeEntrySource())

    panel.startBtn.click()

    assert orch2.started == 1
    assert orch1.started == 0


def test_unbinding_disconnects_the_entry_source(qapp):
    """unbindOrchestrator() must disconnect exactly what bindOrchestrator()
    connected, including the entry-source subscription -- a signal emitted by
    an entry source this panel is no longer bound to must be ignored."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    entrySource = _FakeEntrySource()
    panel.bindOrchestrator(orch, entrySource)
    panel.unbindOrchestrator()

    entrySource.sigActionEntry.emit(object(), ActionLogEntry("Patch"), "started")

    assert panel.currentActionLabel.text() == ""


def test_status_and_current_action_share_the_first_row(qapp):
    """The status indicator and the current-action message sit in one QHBoxLayout
    (statusLabel, a stretch, then currentActionLabel) that is the panel's first
    row; the Start/Stop/Pause/Next buttons are a separate row below it."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    outer = panel.layout()

    statusRow = outer.itemAt(0).layout()
    assert statusRow is not None
    assert statusRow.itemAt(0).widget() is panel.statusLabel
    assert statusRow.itemAt(1).spacerItem() is not None  # the addStretch()
    assert statusRow.itemAt(2).widget() is panel.currentActionLabel

    btnRow = outer.itemAt(1).layout()
    assert btnRow is not None
    buttons = {btnRow.itemAt(i).widget() for i in range(btnRow.count())}
    assert buttons == {panel.startBtn, panel.stopBtn, panel.pauseBtn, panel.nextBtn}


def test_no_protocol_loaded_disables_every_action_button(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    assert not panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_protocol_loaded_idle_enables_only_start(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.bindOrchestrator(_FakeOrchestrator(), _FakeEntrySource())

    assert panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_running_enables_stop_pause_next_disables_start(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")

    assert not panel.startBtn.isEnabled()
    assert panel.stopBtn.isEnabled()
    assert panel.pauseBtn.isEnabled()
    assert panel.nextBtn.isEnabled()


def test_paused_disables_next_keeps_stop_and_pause_enabled(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    orch.sigStatus.emit("paused")

    assert not panel.startBtn.isEnabled()
    assert panel.stopBtn.isEnabled()
    assert panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_error_enables_only_stop(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    orch.sigStatus.emit("error")

    assert not panel.startBtn.isEnabled()
    assert panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_finishing_a_run_returns_to_protocol_loaded_idle_gating(qapp):
    """The orchestrator's own loop emits "waiting" once the queue drains; that
    must re-enable Start and disable Stop/Pause/Next again, same as right
    after a fresh bind."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("running")
    orch.sigStatus.emit("waiting")

    assert panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_unbinding_returns_to_no_protocol_gating(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigStatus.emit("running")

    panel.unbindOrchestrator()

    assert not panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def _boundPanel():
    """A StatusPanel bound to a fake orchestrator, as every test here builds it."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    return panel, orch


def test_surveying_keeps_stop_and_pause_available(qapp):
    # Imaging a tile is slow. An operator who wants out mid-survey must not
    # have to wait for the producer to find a cell first.
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")

    assert panel.stopBtn.isEnabled()
    assert panel.pauseBtn.isEnabled()
    assert not panel.startBtn.isEnabled()


def test_surveying_disables_next_cell(qapp):
    # A next-cell request during a refill is discarded by design (nothing is
    # running and nothing is queued to advance past), so the button must not
    # invite a press that does nothing.
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")

    assert not panel.nextBtn.isEnabled()


def test_surveying_shows_in_the_status_label(qapp):
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")
    assert panel.statusLabel.text() == "surveying"


def test_surveying_locks_area_4(qapp):
    # A run is in flight, so the protocol picker must stay locked -- reloading
    # a protocol mid-survey is the second-orchestrator hazard.
    panel, orch = _boundPanel()
    locked = []
    panel.sigInteractionLocked.connect(locked.append)
    orch.sigStatus.emit("surveying")
    assert locked[-1] is True


def test_surveying_keeps_pause_labeled_pause(qapp):
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")
    assert panel.pauseBtn.text() == "Pause"


def test_status_is_re_emitted_for_panels_that_must_not_touch_the_orchestrator(qapp):
    # The window needs the status to refresh Area 2's survey readout, but the
    # orchestrator is a parentless QObject and must not hold a reference back
    # to the window. This passthrough is that indirection.
    panel, orch = _boundPanel()
    seen = []
    panel.sigStatusChanged.connect(seen.append)

    orch.sigStatus.emit("surveying")
    orch.sigStatus.emit("waiting")

    assert seen == ["surveying", "waiting"]


def test_the_status_passthrough_stops_on_unbind(qapp):
    panel, orch = _boundPanel()
    seen = []
    panel.sigStatusChanged.connect(seen.append)

    panel.unbindOrchestrator()
    orch.sigStatus.emit("surveying")

    assert seen == []


def _record(exc_type="RuntimeError", message="boom", cell_repr="'c1'"):
    from acq4.experiment.error_record import RunErrorRecord

    return RunErrorRecord(exc_type, message, "Traceback...\n", cell_repr)


def test_error_band_shows_the_headline(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record("BrokenPipette", "tip sheared off"))
    assert panel.instructionLabel.text() == "BrokenPipette: tip sheared off"
    assert panel.lastError().exc_type == "BrokenPipette"


def test_error_band_survives_the_waiting_status_that_follows_a_halt(qapp):
    # The regression this whole area needed: Orchestrator._runLoopBody's finally
    # emits "waiting" straight behind the "error" (pinned by
    # test_the_error_status_does_not_stick_after_a_halt), so a band gated on the
    # status is shown and hidden within the same run and the operator sees
    # nothing. Visibility keys off having a record instead.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.show()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    orch.sigStatus.emit("error")
    orch.sigStatus.emit("waiting")
    assert panel.instructionLabel.isVisibleTo(panel) is True
    assert panel.instructionLabel.text() == "RuntimeError: boom"
    assert panel.showInLogBtn.isVisibleTo(panel) is True
    panel.hide()


def test_band_is_hidden_with_no_error(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigStatus.emit("running")
    assert panel.lastError() is None
    assert panel.instructionLabel.isVisibleTo(panel) is False
    assert panel.showInLogBtn.isVisibleTo(panel) is False


def test_a_bare_error_status_with_no_run_error_record_keeps_the_band_hidden(qapp):
    # Guards against _onStatus growing a status == "error" visibility check
    # alongside the record-based one in _updateErrorBand: since a halting run
    # always emits "error" then "waiting" (see
    # test_error_band_survives_the_waiting_status_that_follows_a_halt), such a
    # check would show the band on every error status even with no
    # sigRunError behind it, e.g. before Orchestrator has ever emitted one.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.show()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())

    orch.sigStatus.emit("error")

    assert panel.lastError() is None
    assert panel.instructionLabel.isVisibleTo(panel) is False
    assert panel.showInLogBtn.isVisibleTo(panel) is False
    assert panel.instructionLabel.text() == ""
    panel.hide()


def test_starting_a_new_run_clears_the_previous_error(qapp):
    # The band is a headline for the run that is showing, not a scar.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    orch.sigStatus.emit("waiting")
    panel.startBtn.click()
    assert panel.lastError() is None
    assert panel.instructionLabel.text() == ""
    assert panel.instructionLabel.isVisibleTo(panel) is False
    assert orch.started == 1


def test_unbinding_clears_the_error_and_stops_listening(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    panel.unbindOrchestrator()
    assert panel.lastError() is None
    # The outgoing orchestrator must no longer be able to write into this panel.
    orch.sigRunError.emit(_record("KeyError", "late arrival"))
    assert panel.lastError() is None
    assert panel.instructionLabel.text() == ""


def test_show_in_log_button_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr("acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow())
    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    panel.showInLogBtn.click()
    assert raised == [True]


def test_an_instruction_shows_in_the_band(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    panel.setInstruction("storage", "Storage directory has not been set.")

    assert panel.instructionLabel.isVisibleTo(panel)
    assert panel.instructionLabel.text() == "Storage directory has not been set."


def test_an_instruction_offers_no_log_link(qapp):
    # Show in log narrows the log to a run's records. An instruction is
    # guidance about a click that never started a run, so there is nothing
    # there to show and a button that led nowhere would be worse than none.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    panel.setInstruction("storage", "Storage directory has not been set.")

    assert not panel.showInLogBtn.isVisibleTo(panel)


def test_clearing_an_instruction_empties_the_band(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel.setInstruction("storage", "")

    assert panel.instruction() == ""
    assert not panel.instructionLabel.isVisibleTo(panel)


def test_a_run_error_still_wins_the_band(qapp):
    # A failure that halted a run is about tissue and a pipette in it; guidance
    # about a button is not. The error is the more urgent of the two and must
    # not be displaced by a stale instruction.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    record = _record()
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel._onRunError(record)

    assert record.exc_message in panel.instructionLabel.text()
    assert panel.showInLogBtn.isVisibleTo(panel)


def test_the_instruction_comes_back_once_the_error_clears(qapp):
    # The band holds two independent things. Whatever the instruction asked for
    # has not been done in the meantime, so it is held rather than overwritten.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("storage", "Storage directory has not been set.")
    panel._onRunError(_record())

    panel.clearError()

    assert panel.instructionLabel.text() == "Storage directory has not been set."
    assert not panel.showInLogBtn.isVisibleTo(panel)


def test_a_higher_priority_source_wins_the_band(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    panel.setInstruction("imagery", "Pin reference frames.")
    panel.setInstruction("storage", "Storage directory has not been set.")

    assert panel.instruction() == "Storage directory has not been set."


def test_clearing_one_source_does_not_erase_another(qapp):
    # The property the whole change exists for. newSlice() can fail at
    # create_data_dir with the previous slice still installed, so the storage
    # message and the imagery instruction can want the band at the same time,
    # and whichever cleared last must not take the other down with it.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("imagery", "Pin reference frames.")
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel.setInstruction("storage", "")

    assert panel.instruction() == "Pin reference frames."


def test_a_lower_priority_source_does_not_displace_a_higher_one(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel.setInstruction("imagery", "Pin reference frames.")

    assert panel.instruction() == "Storage directory has not been set."


def test_an_unknown_source_is_a_programming_error(qapp):
    # A typo'd source would otherwise write into a slot nothing ever renders,
    # failing silently and looking exactly like a band that was not updated.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    with pytest.raises(ValueError, match="pinned"):
        panel.setInstruction("pinned", "Pin reference frames.")
