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

    panel.startBtn.click()
    panel.pauseBtn.click()
    panel.stopBtn.click()
    panel.nextBtn.click()

    assert orch.started == 1
    assert orch.paused == 1
    assert orch.stopped == 1
    assert orch.nexted == 1


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
