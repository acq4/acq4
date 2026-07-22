"""Tests for FSM-wrapping composite Actions (drive PatchPipette FSM to a terminal)."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.fsm import PatchAction, ResealAction, FsmCompositeAction
from acq4.experiment.exceptions import BrokenPipette
from acq4.experiment.registry import get_action_class


def _ctx(pip):
    return ExecutionContext(pipette=pip)


def test_patch_reaches_whole_cell(fake_pip_factory):
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    a = PatchAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "whole cell"
    assert pip.setState_calls[0][0] == "cell detect"


def test_patch_declares_broken_as_outcome(fake_pip_factory):
    # broken IS a declared Patch outcome -> routes as outcome, not exception
    pip = fake_pip_factory(["cell detect", "broken"])
    a = PatchAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "broken"


def test_reseal_reaches_outside_out(fake_pip_factory):
    pip = fake_pip_factory(["reseal", "outside out"])
    a = ResealAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "outside out"


def test_reseal_broken_raises_exception(fake_pip_factory):
    # broken is NOT a Reseal outcome -> mapped to BrokenPipette
    pip = fake_pip_factory(["reseal", "broken"])
    a = ResealAction()
    a.poll_interval = 0
    with pytest.raises(BrokenPipette):
        a.run(_ctx(pip))


def test_registered():
    assert get_action_class("Patch") is PatchAction
    assert get_action_class("Reseal") is ResealAction


def test_missing_entry_state_raises(fake_pip_factory):
    class Bare(FsmCompositeAction):
        outcomes = ("x",)

    pip = fake_pip_factory([])
    with pytest.raises(ValueError):
        Bare().run(_ctx(pip))


def test_safeabort_retracts_to_bath(fake_pip_factory):
    pip = fake_pip_factory([])
    PatchAction().safeAbort(_ctx(pip))
    assert ("bath", {}) in pip.setState_calls
