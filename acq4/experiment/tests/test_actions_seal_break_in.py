"""Tests for the seal and break_in FSM actions, which split patch() at a held
cell-attached state."""

import pytest

from acq4.experiment.actions import break_in, seal
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import OrchestrationError

from .conftest import FakePatchPipette, FakeStateJob


class _HoldableJob(FakeStateJob):
    def __init__(self, name, pipette=None):
        super().__init__(name, pipette)
        self.holdCalls = 0
        # States the pipette had walked through when hold() was first called.
        self.heldAfter = None

    def hold(self):
        self.holdCalls += 1
        if self.heldAfter is None:
            self.heldAfter = list(self._pipette.walked)

    def isHolding(self):
        return self.holdCalls > 0


class _HoldablePipette(FakePatchPipette):
    """FakePatchPipette whose state jobs persist per entry and can be held."""

    def __init__(self, state_sequence=(), start="out"):
        super().__init__(state_sequence)
        self.walked = []
        self.jobs = []
        self._job = _HoldableJob(start, self)
        self._current = start

    def changeState(self, state):
        # The job exists before the change is announced, as in PatchPipetteStateManager.
        self._job = _HoldableJob(state, self)
        self.jobs.append(self._job)
        self.walked.append(state)
        super().changeState(state)

    def getState(self):
        return self._job


def _ctx(pip, **kwargs):
    return ExecutionContext(pipette=pip, **kwargs)


def _details(ctx):
    seen = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: seen.append((kind, payload))

    ctx.on_log_action = hook
    return seen


def _job(pip, state):
    return [j for j in pip.jobs if j.stateName == state][-1]


# -- seal ---------------------------------------------------------------------


def test_seal_enters_at_approach_and_stops_at_cell_attached():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached"])
    assert seal(_ctx(pip)) == "cell attached"
    assert pip.setState_calls[0][0] == "approach"


def test_seal_holds_cell_attached_during_the_state_change():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached"])
    seal(_ctx(pip))
    job = _job(pip, "cell attached")
    assert job.isHolding()
    # Held from the state-change notification, before anything else happened.
    assert job.heldAfter == ["approach", "cell detect", "seal", "cell attached"]


def test_seal_holds_no_other_state():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached"])
    seal(_ctx(pip))
    assert [j.stateName for j in pip.jobs if j.isHolding()] == ["cell attached"]


@pytest.mark.parametrize("outcome", ["bath", "broken", "fouled"])
def test_seal_returns_patch_outcomes(outcome):
    pip = _HoldablePipette(["cell detect", outcome])
    assert seal(_ctx(pip)) == outcome


def test_seal_returns_whole_cell_after_spontaneous_break_in_while_sealing():
    pip = _HoldablePipette(["cell detect", "seal", "break in", "whole cell"])
    assert seal(_ctx(pip)) == "whole cell"


def test_seal_raises_if_the_pipette_left_cell_attached():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached", "fouled"])
    with pytest.raises(OrchestrationError, match="left 'cell attached'"):
        seal(_ctx(pip))


def test_seal_retains_a_test_pulse_history_payload():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached"])
    ctx = _ctx(pip)
    seen = _details(ctx)
    seal(ctx)
    kind, payload = seen[0]
    assert kind == "test_pulse_history"
    assert payload["entry_state"] == "approach"
    assert payload["reached"] == "cell attached"


def test_seal_forwards_entry_config_to_approach():
    pip = _HoldablePipette(["cell attached"])
    seal(_ctx(pip), approachSpeed=1e-3, record_events=False)
    assert pip.setState_calls[0] == ("approach", {"approachSpeed": 1e-3})


def test_seal_does_not_checkpoint_at_entry():
    calls = []
    pip = _HoldablePipette(["cell attached"])
    seal(_ctx(pip, checkpoint=lambda: calls.append("checkpoint")))
    assert calls == []


# -- break_in -----------------------------------------------------------------


def test_break_in_enters_break_in_from_cell_attached():
    pip = _HoldablePipette(["whole cell"], start="cell attached")
    assert break_in(_ctx(pip)) == "whole cell"
    assert pip.setState_calls[0][0] == "break in"


@pytest.mark.parametrize("outcome", ["broken", "fouled"])
def test_break_in_returns_failure_outcomes(outcome):
    pip = _HoldablePipette([outcome], start="cell attached")
    assert break_in(_ctx(pip)) == outcome


@pytest.mark.parametrize("start", ["whole cell", "bath", "out"])
def test_break_in_refuses_outside_cell_attached(start):
    pip = _HoldablePipette(["whole cell"], start=start)
    with pytest.raises(OrchestrationError, match="not 'cell attached'"):
        break_in(_ctx(pip))
    assert pip.setState_calls == []


def test_break_in_forwards_entry_config():
    pip = _HoldablePipette(["whole cell"], start="cell attached")
    break_in(_ctx(pip), pulseInterval=3.0)
    assert pip.setState_calls[0] == ("break in", {"pulseInterval": 3.0})


def test_seal_then_break_in():
    pip = _HoldablePipette(["cell detect", "seal", "cell attached"])
    ctx = _ctx(pip)
    assert seal(ctx) == "cell attached"
    pip._seq = ["whole cell"]
    assert break_in(ctx) == "whole cell"
