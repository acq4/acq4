"""Regression tests for AutopatchWindow.teardown(): the Orchestrator/Cell
QObjects must be unwired from the window's panels (and the orchestrator
stopped) deterministically on close, rather than left for Python's
non-deterministic cyclic GC to eventually reclaim -- which can free live
QObjects outside Qt's safe teardown path and crash the process on exit."""
import gc
import os
import weakref

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
    the way a real PatchPipette delegates target lookups to its manipulator."""

    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakeCameraSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


_NOOP_PROTOCOL = '''"""Teardown test fixture: opens and immediately closes one log_action entry.
Used by the weakref/gc proof, which never starts the orchestrator (see that
test's docstring for why) but does run this protocol synchronously via
run_sync_cell(), so the on_log_action wiring this task adds is exercised by
that proof too -- not just resolving immediately without touching ctx."""


def run(ctx, **kwargs):
    with ctx.log_action("Noop") as entry:
        entry.set_status("doing nothing in particular")
'''

_SLOW_PROTOCOL = '''"""Teardown test fixture: loops until stopped. Used to prove
AutopatchWindow.teardown() actually stops an in-flight run rather than
abandoning it."""
from acq4.util.task import check_stop, sleep


def run(ctx, **kwargs):
    while True:
        check_stop()
        sleep(0.01)
'''


def _write_protocol(path, name, body):
    with open(os.path.join(path, name), "w") as fh:
        fh.write(body)


def test_teardown_breaks_the_orchestrator_cell_window_cycle(qapp, tmp_path):
    """Load a protocol and seed a cell (but do not start the orchestrator --
    see the note below), tear the window down, and prove -- with the cyclic GC
    disabled -- that plain refcounting (no gc.collect()) is enough to free the
    orchestrator, the seeded cell, and the window afterward.

    Before the fix, StatusPanel/CellPanel held live signal connections to the
    Orchestrator (and the Orchestrator/window held references back to them),
    so the whole graph was a genuine reference cycle only the cyclic collector
    could break.

    This deliberately never calls orchestrator.start(): doing so hands the
    orchestrator to gentletask as a ThreadTask whose stored target is a bound
    method of the orchestrator itself (`self._task._fn is orchestrator._runLoopBody`),
    which is its own independent reference cycle -- permanent only while that
    run is in flight, since _onLoopFinished breaks it once the run completes.
    It is unrelated to the window/panel wiring this fix addresses, and out of
    scope here since it lives in acq4/experiment + the separate gentletask
    library. A second test below starts the orchestrator to prove teardown()
    stops an in-flight run; it does not repeat this refcounting proof.
    """
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)

    gc.disable()
    try:
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
        seededCell = list(win.cellPanel._cells.values())[0]
        # Select the row before running so the run below actually populates
        # _timelineItems, making the empty-dict assertions after it meaningful.
        win.cellPanel.cellList.setCurrentRow(0)

        orchestrator = win.orchestrator
        assert orchestrator is not None
        # Sanity check the cycle actually exists pre-teardown: the orchestrator
        # is cross-wired to both panels via signal connections.
        assert win.statusPanel._orchestrator is orchestrator
        assert win.cellPanel._orchestrator is orchestrator

        # Actually run the protocol synchronously (main thread; no gentletask
        # ThreadTask involved, so this does not hit the independent
        # ThreadTask/orchestrator cycle the docstring above rules out of
        # scope), so ctx.log_action() -> CellPanel.onLogAction -> the entry's
        # on_status/on_widget/on_finish callbacks all actually run -- exactly
        # the new reference path this task adds (an ActionLogEntry's
        # callbacks closing over CellPanel) -- before proving the whole graph
        # is still freed by plain refcounting below.
        orchestrator.run_sync_cell(seededCell)
        win.cellPanel.cellList.setCurrentRow(0)
        assert win.cellPanel.timelineList.count() == 1
        assert "Noop" in win.cellPanel.timelineList.item(0).text()
        # No stale per-entry bookkeeping left behind once the entry finished --
        # if onLogAction's wiring held onto the entry itself instead of just
        # its id, this would still show it.
        assert win.cellPanel._entryTimelineLoc == {}
        assert win.cellPanel._timelineItems == {}

        orchestrator_ref = weakref.ref(orchestrator)
        cell_ref = weakref.ref(seededCell)
        window_ref = weakref.ref(win)
        statusPanel_ref = weakref.ref(win.statusPanel)
        cellPanel_ref = weakref.ref(win.cellPanel)

        win.teardown()

        # No panel still references the orchestrator once torn down.
        assert win.statusPanel._orchestrator is None
        assert win.cellPanel._orchestrator is None
        assert win.orchestrator is None
        assert win.cellPanel._cells == {}

        del orchestrator, seededCell
        win.close()  # exercises the closeEvent path too; teardown() is idempotent
        del win
        # No gc.collect() below -- pure refcounting only, since gc is disabled.

        assert orchestrator_ref() is None, "orchestrator should be freed by refcounting alone"
        assert cell_ref() is None, "seeded cell should be freed by refcounting alone"
        assert window_ref() is None, "window should be freed by refcounting alone"
        assert statusPanel_ref() is None, "StatusPanel should be freed by refcounting alone"
        assert cellPanel_ref() is None, "CellPanel should be freed by refcounting alone"
    finally:
        gc.enable()


def test_teardown_stops_an_in_flight_orchestrator_run(qapp, qtbot, tmp_path):
    """teardown() must stop a currently-running orchestrator rather than
    abandon it, and leave no panel still bound to it afterward."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "slow.py", _SLOW_PROTOCOL)

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
        cameraSelector=_FakeCameraSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("slow")
    win.protocolPanel.loadSelected()
    win.cellPanel.addFromTargetBtn.click()

    win.statusPanel.startBtn.click()
    task = win.orchestrator._task
    assert task is not None
    # Give the worker thread a moment to actually enter the slow action's loop.
    qtbot.wait(50)
    assert not task.is_done

    win.teardown()

    assert task.is_done
    assert task.is_stopped
    assert win.orchestrator is None
    assert win.statusPanel._orchestrator is None
    assert win.cellPanel._orchestrator is None

    win.close()
