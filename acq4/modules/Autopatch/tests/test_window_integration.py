"""Integration test: loading a protocol builds and binds a fresh Orchestrator
to the window's StatusPanel/CellPanel, and a seeded cell runs end-to-end."""
import json
import os

import pytest

from acq4.experiment.action import Action
from acq4.experiment.registry import register_action
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakePipetteSelector(Qt.QWidget):
    """Stands in for InterfaceCombo so the test never triggers its internal
    getManager() call."""

    def __init__(self, target=None):
        super().__init__()
        self._target = target

    def getSelectedObj(self):
        if self._target is None:
            return None
        return _FakePipette(self._target)


class _FakePipette:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakeCameraSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


def _write_protocol(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoToNext", "params": {}}},
        "edges": [],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_loading_a_protocol_builds_and_binds_an_orchestrator(qapp, tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.json")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo.json")
    win.protocolPanel.loadSelected()

    assert win.orchestrator is not None
    assert win.orchestrator.protocol is win.protocolPanel.protocol
    # StatusPanel/CellPanel are bound: clicking Start reaches the real orchestrator.
    win.statusPanel.startBtn.click()
    win.orchestrator.wait(timeout=2)


@register_action(name="AutopatchIntegrationNoop")
class _NoopAction(Action):
    """A trivial Action used only by this test: logs via ctx.log and always
    resolves to 'done', so a seeded cell can run through to completion."""

    outcomes = ("done",)

    def run(self, ctx):
        ctx.log(f"ran on {ctx.cell!r}")
        return "done"


def _write_noop_protocol(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "AutopatchIntegrationNoop", "params": {}}},
        "edges": [],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_full_flow_seeds_a_cell_starts_and_updates_status_timeline_log(qapp, qtbot, tmp_path):
    """Headless end-to-end check: load protocol -> seed a cell via "Add from
    target" -> Start -> status/timeline/log all reflect the run.

    The orchestrator runs its queue on a worker thread and marshals signals back
    to the GUI thread via queued connections, so this test uses qtbot.waitUntil
    (which pumps the Qt event loop) rather than a bare Orchestrator.wait().
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_noop_protocol(tmp_path, "demo.json")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo.json")
    win.protocolPanel.loadSelected()

    win.cellPanel.addFromTargetBtn.click()
    assert win.cellPanel.cellList.count() == 1
    assert "queued" in win.cellPanel.cellList.item(0).text()

    win.statusPanel.startBtn.click()
    qtbot.waitUntil(lambda: "done" in win.cellPanel.cellList.item(0).text(), timeout=2000)

    assert "waiting" in win.statusPanel.statusLabel.text().lower()

    win.cellPanel.cellList.setCurrentRow(0)
    timelineLines = [
        win.cellPanel.timelineList.item(i).text()
        for i in range(win.cellPanel.timelineList.count())
    ]
    assert timelineLines == ["n1: done"]  # action.name is the protocol node id

    assert "ran on" in win.cellPanel.logView.toPlainText()


class _CountingPipetteSelector(Qt.QWidget):
    """Like _FakePipetteSelector, but counts getSelectedObj() calls and allows
    mutating the "selection" mid-test, so a test can prove the context factory
    reads a cached pipette rather than re-consulting the selector widget."""

    def __init__(self, target):
        super().__init__()
        self._target = target
        self.callCount = 0

    def getSelectedObj(self):
        self.callCount += 1
        return _FakePipette(self._target)

    def setTarget(self, target) -> None:
        self._target = target


@register_action(name="AutopatchPipetteCaptureA")
class _CapturePipetteA(Action):
    """Captures ctx.pipette on its `results`, then advances to the next node."""

    outcomes = ("next",)

    def run(self, ctx):
        self.results["pipette"] = ctx.pipette
        return "next"


@register_action(name="AutopatchPipetteCaptureB")
class _CapturePipetteB(Action):
    """Captures ctx.pipette on its `results`, then finishes the cell."""

    outcomes = ("done",)

    def run(self, ctx):
        self.results["pipette"] = ctx.pipette
        return "done"


def _write_pipette_capture_protocol(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {
            "n1": {"type": "AutopatchPipetteCaptureA", "params": {}},
            "n2": {"type": "AutopatchPipetteCaptureB", "params": {}},
        },
        "edges": [{"from": "n1", "outcome": "next", "to": "n2"}],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_pipette_is_snapshotted_at_start_not_read_from_selector_mid_run(qapp, qtbot, tmp_path):
    """The context factory must not call the pipette selector widget from the
    orchestrator's worker thread during a run (a race on currentIndex()/
    interfaceMap). It should read a plain object cached at Start (GUI thread)."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_pipette_capture_protocol(tmp_path, "demo.json")

    selector = _CountingPipetteSelector(target=(1e-3, 2e-3, 3e-3))
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=selector,
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo.json")
    win.protocolPanel.loadSelected()

    win.cellPanel.addFromTargetBtn.click()
    assert win.cellPanel.cellList.count() == 1

    callsBeforeStart = selector.callCount
    win.statusPanel.startBtn.click()
    # Simulate the operator changing the pipette selection immediately after
    # Start -- the in-flight run (both of its nodes) must not notice.
    selector.setTarget((9e-3, 9e-3, 9e-3))

    qtbot.waitUntil(lambda: "done" in win.cellPanel.cellList.item(0).text(), timeout=2000)

    nodeA = win.orchestrator.protocol.nodes["n1"]
    nodeB = win.orchestrator.protocol.nodes["n2"]
    assert nodeA.results["pipette"] is nodeB.results["pipette"]
    assert nodeA.results["pipette"].targetPosition() == pytest.approx((1e-3, 2e-3, 3e-3))
    # Resolved exactly once (at Start) -- not once per node during _walk, and
    # not affected by the mid-run mutation above.
    assert selector.callCount == callsBeforeStart + 1
