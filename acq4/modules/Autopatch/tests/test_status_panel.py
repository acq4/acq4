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
    assert panel.instructionLabel.isVisible()


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
