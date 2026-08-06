# Tests for Autopatcher._autopatchCellPatch — cancelling the demo must also cancel
# the PatchPipette FSM state job the demo put the pipette into.
import time
from unittest.mock import MagicMock

import pytest

from acq4.modules.AutomationDebug.autopatch import Autopatcher
from acq4.util.task import Stopped, asynch


def _window_with_stuck_fsm():
    """A window whose pipette reports a non-terminal FSM state forever, so the
    patch poll loop only ever ends by being stopped."""
    win = MagicMock()
    job = MagicMock()
    job.stateName = "approach"
    win.patchPipetteDevice.setState.return_value = job
    win.patchPipetteDevice.getState.return_value = job
    return win, job


def _run_until_entered(autopatcher, ppip):
    """Start _autopatchCellPatch in a task and return it once it has entered the
    FSM (so a stop lands mid-poll rather than before the body runs)."""
    task = asynch(autopatcher._autopatchCellPatch, name="autopatch demo")(MagicMock())
    deadline = time.time() + 5
    while not ppip.setState.called and time.time() < deadline:
        time.sleep(0.01)
    assert ppip.setState.called, "patch loop never entered the approach state"
    return task


def test_stopping_the_demo_cancels_the_patch_state_job():
    """A PatchPipetteState job is a detached task owned by the state manager, so a
    cooperative stop of the demo does not cascade into it. Without an explicit
    cancel the pipette keeps driving approach -> cell detect -> seal after the
    operator has pressed the demo button to stop."""
    win, job = _window_with_stuck_fsm()
    autopatcher = Autopatcher(win)

    task = _run_until_entered(autopatcher, win.patchPipetteDevice)
    task.stop("user requested cancel")
    with pytest.raises(Stopped):
        task.wait(timeout=5)

    job.stop.assert_called_once()
    assert job.stop.call_args.kwargs.get("wait") is True


class TestCleanPipetteIfNeeded:
    @staticmethod
    def _window(clean_before, clean_after=None):
        win = MagicMock()
        ppip = win.patchPipetteDevice
        ppip.isTipClean.side_effect = [clean_before, clean_after]
        return win

    def test_skips_the_clean_when_the_tip_is_already_clean(self):
        win = self._window(clean_before=True)
        assert Autopatcher(win)._cleanPipetteIfNeeded() is True
        win.patchPipetteDevice.setState.assert_not_called()

    def test_cleans_and_dips_when_the_tip_is_fouled(self):
        win = self._window(clean_before=False, clean_after=True)
        assert Autopatcher(win)._cleanPipetteIfNeeded() is True
        win.patchPipetteDevice.setState.assert_called_once_with("clean", nextState="bath")
        win.scopeDevice.moveDip.assert_called_once()

    def test_quits_when_the_clean_fails(self):
        win = self._window(clean_before=False)
        win.patchPipetteDevice.setState.return_value.wait.side_effect = RuntimeError("boom")
        assert Autopatcher(win)._cleanPipetteIfNeeded() is False

    def test_quits_when_the_tip_is_still_fouled_afterwards(self):
        win = self._window(clean_before=False, clean_after=False)
        assert Autopatcher(win)._cleanPipetteIfNeeded() is False
        win.scopeDevice.moveDip.assert_not_called()

    def test_propagates_an_operator_cancel(self):
        """Stopped is an Exception, so a cancel during the clean would otherwise be
        caught as a clean failure -- ending the demo normally, which the button
        reports as a successful run."""
        win = self._window(clean_before=False)
        win.patchPipetteDevice.setState.return_value.wait.side_effect = Stopped("cancelled")
        with pytest.raises(Stopped):
            Autopatcher(win)._cleanPipetteIfNeeded()


def test_reaching_a_terminal_state_does_not_cancel_the_state_job():
    """The cancel is for an interrupted run only: a patch that ends normally must
    leave the pipette resting in the terminal state it reached."""
    win, job = _window_with_stuck_fsm()
    job.stateName = "whole cell"
    autopatcher = Autopatcher(win)

    assert autopatcher._autopatchCellPatch(MagicMock()) == "whole cell"
    job.stop.assert_not_called()
