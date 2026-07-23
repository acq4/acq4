"""Tests for StatusPanel: Start/Stop/Pause/Next wired to an Orchestrator, and
sigStatus/sigCurrentAction reflected in the status + current-action labels."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)
    sigCurrentAction = Qt.Signal(object, object)

    def __init__(self):
        super().__init__()
        self.started = self.stopped = self.paused = self.resumed = self.nexted = 0

    def start(self):
        self.started += 1

    def stop(self, reason=""):
        self.stopped += 1

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def requestNextCell(self):
        self.nexted += 1


def test_buttons_drive_the_bound_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

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


def test_pause_button_toggles_to_resume_while_paused(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

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
    panel.bindOrchestrator(orch)

    orch.sigStatus.emit("running")
    assert "running" in panel.statusLabel.text().lower()

    orch.sigStatus.emit("error")
    assert "error" in panel.statusLabel.text().lower()
    assert panel.instructionLabel.isVisible()


def test_current_action_signal_updates_label(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    class _Cell:
        def __repr__(self):
            return "cell-1"

    class _Action:
        name = "Patch"

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    orch.sigCurrentAction.emit(_Cell(), _Action())
    assert "Patch" in panel.currentActionLabel.text()
    assert "cell-1" in panel.currentActionLabel.text()

    orch.sigCurrentAction.emit(None, None)
    assert panel.currentActionLabel.text() == ""


def test_rebinding_disconnects_previous_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch1 = _FakeOrchestrator()
    orch2 = _FakeOrchestrator()
    panel.bindOrchestrator(orch1)
    panel.bindOrchestrator(orch2)

    panel.startBtn.click()

    assert orch2.started == 1
    assert orch1.started == 0


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
    panel.bindOrchestrator(_FakeOrchestrator())

    assert panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()


def test_running_enables_stop_pause_next_disables_start(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    orch.sigStatus.emit("running")

    assert not panel.startBtn.isEnabled()
    assert panel.stopBtn.isEnabled()
    assert panel.pauseBtn.isEnabled()
    assert panel.nextBtn.isEnabled()


def test_paused_disables_next_keeps_stop_and_pause_enabled(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

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
    panel.bindOrchestrator(orch)

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
    panel.bindOrchestrator(orch)

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
    panel.bindOrchestrator(orch)
    orch.sigStatus.emit("running")

    panel.unbindOrchestrator()

    assert not panel.startBtn.isEnabled()
    assert not panel.stopBtn.isEnabled()
    assert not panel.pauseBtn.isEnabled()
    assert not panel.nextBtn.isEnabled()
