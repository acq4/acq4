"""Integration test: loading a protocol builds and binds a fresh Orchestrator
to the window's StatusPanel/CellPanel, and a seeded cell runs end-to-end."""
import os

import pytest

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
    """Stands in for a PatchPipette: exposes .pipetteDevice.targetPosition()
    the way a real PatchPipette delegates target lookups to its manipulator,
    plus a direct targetPosition() convenience so tests can assert on the
    cached ctx.pipette's value without reaching into .pipetteDevice."""

    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)

    def targetPosition(self):
        return self.pipetteDevice.targetPosition()


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakeCameraSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


_NOOP_PROTOCOL = '''"""Integration test fixture: resolves immediately without touching ctx."""


def run(ctx, **kwargs):
    return None
'''


def _write_protocol(path, name, body):
    with open(os.path.join(path, name), "w") as fh:
        fh.write(body)


def test_loading_a_protocol_builds_and_binds_an_orchestrator(qapp, tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")
    win.protocolPanel.loadSelected()

    assert win.orchestrator is not None
    assert win.orchestrator.protocolFile is win.protocolPanel.protocolFile
    # StatusPanel/CellPanel are bound: clicking Start reaches the real orchestrator.
    win.statusPanel.startBtn.click()
    win.orchestrator.wait(timeout=2)


_NOOP_LOGGING_PROTOCOL = '''"""Integration test fixture: logs via ctx.log and opens a single log_action, so
a seeded cell can run through to completion while exercising both the log
view and the Area 5 timeline."""


def run(ctx, **kwargs):
    ctx.log(f"ran on {ctx.cell!r}")
    with ctx.log_action("Noop") as entry:
        entry.set_status("doing nothing in particular")
'''


def _write_noop_protocol(path, name):
    _write_protocol(path, name, _NOOP_LOGGING_PROTOCOL)


def test_full_flow_seeds_a_cell_starts_and_updates_status_timeline_log(qapp, qtbot, tmp_path):
    """Headless end-to-end check: load protocol -> seed a cell via "Add from
    target" -> Start -> status/timeline/log all reflect the run.

    The orchestrator runs its queue on a worker thread and marshals signals back
    to the GUI thread via queued connections, so this test uses qtbot.waitUntil
    (which pumps the Qt event loop) rather than a bare Orchestrator.wait().
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_noop_protocol(tmp_path, "demo.py")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")
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
    # A timeline row's label comes from the ctx.log_action() name ("Noop" here,
    # opened once by the protocol above) rather than a graph node id; the
    # elapsed-time suffix is non-deterministic, so check the fixed prefix only.
    assert len(timelineLines) == 1
    assert timelineLines[0].startswith("Noop — ✓ done")

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


_PIPETTE_CAPTURE_PROTOCOL = '''"""Integration test fixture: reads ctx.pipette at two separate points in the
protocol body and stashes both onto ctx.cell, so the test can assert (without
an Action's `results` dict, which no longer exists) that the SAME pipette
object was seen both times -- i.e. the whole protocol shares one ExecutionContext
per cell, built once at the start of that cell's run."""


def run(ctx, **kwargs):
    ctx.cell._firstPipette = ctx.pipette
    ctx.cell._secondPipette = ctx.pipette
'''


def _write_pipette_capture_protocol(path, name):
    _write_protocol(path, name, _PIPETTE_CAPTURE_PROTOCOL)


def test_pipette_is_snapshotted_at_start_not_read_from_selector_mid_run(qapp, qtbot, tmp_path):
    """The context factory must not call the pipette selector widget from the
    orchestrator's worker thread during a run (a race on currentIndex()/
    interfaceMap). It should read a plain object cached at Start (GUI thread):
    the resolved pipette's target matches the selector's state at Start
    (not the mid-run mutation below), and the selector is consulted exactly
    once for the whole run."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_pipette_capture_protocol(tmp_path, "demo.py")

    selector = _CountingPipetteSelector(target=(1e-3, 2e-3, 3e-3))
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=selector,
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")
    win.protocolPanel.loadSelected()

    win.cellPanel.addFromTargetBtn.click()
    assert win.cellPanel.cellList.count() == 1
    seededCell = list(win.cellPanel._cells.values())[0]

    callsBeforeStart = selector.callCount
    win.statusPanel.startBtn.click()
    # Simulate the operator changing the pipette selection immediately after
    # Start -- the in-flight run must not notice.
    selector.setTarget((9e-3, 9e-3, 9e-3))

    qtbot.waitUntil(lambda: hasattr(seededCell, "_secondPipette"), timeout=2000)

    assert seededCell._firstPipette.targetPosition() == pytest.approx((1e-3, 2e-3, 3e-3))
    # Resolved exactly once (at Start) -- not once per protocol step, and not
    # affected by the mid-run mutation above.
    assert selector.callCount == callsBeforeStart + 1
