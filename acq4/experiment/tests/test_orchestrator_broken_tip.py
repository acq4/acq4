"""A pass that ends with a broken tip documents it, pauses for the operator, and
resumes on a fresh pipette (or stops, if the operator says so).

The trigger is the pipette's own isTipBroken(), not the way the protocol left:
patch() returns "broken" as an ordinary outcome, while other actions raise
BrokenPipette, and both mean the same thing at the rig.
"""
from __future__ import annotations

import pytest

from acq4.experiment import orchestrator as orch_mod
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import BrokenPipette
from acq4.experiment.orchestrator import Orchestrator

from .test_actions_device import FakePipette


class _Cell:
    def __init__(self, name):
        self.position = (0.0, 0.0, -50e-6)
        self.name = name

    def __repr__(self):
        return f"<Cell {self.name}>"


@pytest.fixture
def rig(make_pf, monkeypatch):
    """An orchestrator over a fake pipette, with the documentation and prompt
    seams recorded into one shared `order` list alongside the pipette's moves."""
    pip = FakePipette()
    order = pip.order
    prompts = []
    answers = []

    def fake_document(ctx):
        order.append(("document", ctx.pipette.isTipBroken()))

    def fake_prompt(ctx, message="", title="Prompt", choices=("OK",)):
        prompts.append((message, tuple(choices)))
        order.append(("prompt",))
        return answers.pop(0)

    monkeypatch.setattr(orch_mod, "document_broken_tip", fake_document)
    monkeypatch.setattr(orch_mod, "prompt", fake_prompt)

    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        behaviour = pf.behaviour.pop(0) if pf.behaviour else None
        if behaviour == "break":
            pip.broken = True
            pip.state_name = "broken"
        elif behaviour == "break-raise":
            pip.broken = True
            pip.state_name = "broken"
            raise BrokenPipette("pipette state is 'broken'")

    pf.behaviour = []
    pf.run = run
    orch = Orchestrator(
        pf,
        contextFactory=lambda cell: ExecutionContext(cell=cell, pipette=pip),
    )
    finished = []
    statuses = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c.name, s)))
    orch.sigStatus.connect(statuses.append)

    class Rig:
        pass

    r = Rig()
    r.pip, r.pf, r.orch, r.order = pip, pf, orch, order
    r.prompts, r.answers, r.ran = prompts, answers, ran
    r.finished, r.statuses = finished, statuses
    return r


def _retraction(kinds):
    """Index of the end-of-pass retraction: a park, or a move home when nothing
    is left queued to park clear of."""
    return min(kinds.index(k) for k in ("park", "move") if k in kinds)


def _enqueue(rig, *names):
    for name in names:
        rig.orch.enqueue(_Cell(name))


def test_an_intact_tip_is_neither_documented_nor_prompted_about(rig):
    _enqueue(rig, "c1")

    rig.orch.run_sync()

    assert rig.prompts == []
    assert not any(step[0] == "document" for step in rig.order)
    assert rig.finished == [("c1", "done")]


def test_a_broken_tip_is_documented_before_it_is_parked(rig):
    """The z-stack has to be taken where the tip broke; the park takes it out
    of the slice."""
    rig.pf.behaviour = ["break"]
    rig.answers.append("Pipette replaced")
    _enqueue(rig, "c1")

    rig.orch.run_sync()

    kinds = [step[0] for step in rig.order]
    assert kinds.index("document") < _retraction(kinds) < kinds.index("prompt")
    assert ("document", True) in rig.order


def test_a_broken_pass_is_reported_as_broken(rig):
    rig.pf.behaviour = ["break"]
    rig.answers.append("Pipette replaced")
    _enqueue(rig, "c1")

    rig.orch.run_sync()

    assert rig.finished == [("c1", "broken")]


def test_replacing_the_pipette_resumes_the_run_on_a_fresh_pipette(rig):
    rig.pf.behaviour = ["break"]
    rig.answers.append("Pipette replaced")
    _enqueue(rig, "c1", "c2")

    rig.orch.run_sync()

    assert rig.pip.new_pipette_calls == 1
    assert not rig.pip.isTipBroken()
    assert [c.name for c in rig.ran] == ["c1", "c2"]
    assert rig.finished == [("c1", "broken"), ("c2", "done")]


def test_the_run_reads_paused_while_waiting_on_the_operator(rig):
    rig.pf.behaviour = ["break"]
    rig.answers.append("Pipette replaced")
    _enqueue(rig, "c1")

    rig.orch.run_sync()

    assert "paused" in rig.statuses


def test_the_prompt_names_where_the_tip_broke_and_offers_both_ways_on(rig):
    rig.pip.pipetteDevice.global_position = (1e-3, 2e-3, 50e-6)
    rig.pf.behaviour = ["break"]
    rig.answers.append("Pipette replaced")
    _enqueue(rig, "c1")

    rig.orch.run_sync()

    ((message, choices),) = rig.prompts
    assert "1000.0, 2000.0, 50.0" in message
    assert set(choices) == {"Pipette replaced", "Stop run"}
    # Headless prompts answer with the first choice; that must never be a
    # pipette swap nobody made.
    assert choices[0] == "Stop run"


def test_choosing_stop_ends_the_run_without_an_error(rig):
    rig.pf.behaviour = ["break"]
    rig.answers.append("Stop run")
    errors = []
    rig.orch.sigRunError.connect(errors.append)
    _enqueue(rig, "c1", "c2")

    rig.orch.run_sync()  # a stop ends run_sync normally

    assert [c.name for c in rig.ran] == ["c1"]
    assert rig.pip.new_pipette_calls == 0
    assert errors == []


def test_an_action_raising_broken_pipette_pauses_rather_than_aborting(rig):
    """clean(), reseal() and the rest raise BrokenPipette for a tip that breaks
    under them; that is the same event as patch() returning "broken"."""
    rig.pf.behaviour = ["break-raise"]
    rig.answers.append("Pipette replaced")
    errors = []
    rig.orch.sigRunError.connect(errors.append)
    _enqueue(rig, "c1", "c2")

    rig.orch.run_sync()

    assert errors == []
    assert rig.finished == [("c1", "broken"), ("c2", "done")]
    kinds = [step[0] for step in rig.order]
    assert kinds.index("document") < _retraction(kinds)
