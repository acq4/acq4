"""Tests for exception dispatch to handler sub-protocols."""
import pytest

from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.exceptions import AbortExperiment


def test_no_handler_aborts(raising_cls):
    p = Protocol(nodes={"a": raising_cls(params={"exc": "BrokenPipette"})},
                 edges={}, entry="a")
    with pytest.raises(AbortExperiment):
        Orchestrator(p).run_sync_cell("c1")


def test_handler_advance(recording_cls, raising_cls):
    recording_cls.ran.clear()
    # main: a raises BrokenPipette. handler: h1 (Recording) -> GoToNext.
    from acq4.experiment.actions.flow import GoToNextAction
    handler = Protocol(
        nodes={"h1": recording_cls(name="h1"), "adv": GoToNextAction(name="adv")},
        edges={("h1", "done"): "adv"},
        entry="h1",
    )
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "BrokenPipette"})},
        edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    finished = []
    orch = Orchestrator(p)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert recording_cls.ran == ["h1"]        # handler ran
    assert finished == [("c1", "handled")]


def test_handler_retry_then_success(recording_cls):
    from acq4.experiment.action import Action
    from acq4.experiment.registry import register_action
    from acq4.experiment.exceptions import BrokenPipette
    from acq4.experiment.actions.flow import RetryCellAction

    @register_action(name="FailOnce")
    class FailOnce(Action):
        outcomes = ("done",)
        calls = {"n": 0}

        def run(self, ctx):
            FailOnce.calls["n"] += 1
            if FailOnce.calls["n"] == 1:
                raise BrokenPipette("first attempt fails")
            return "done"

    FailOnce.calls["n"] = 0
    handler = Protocol(nodes={"r": RetryCellAction(name="r")}, edges={}, entry="r")
    p = Protocol(
        nodes={"a": FailOnce(name="a")}, edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    finished = []
    orch = Orchestrator(p)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert FailOnce.calls["n"] == 2           # failed once, retried, succeeded
    assert finished == [("c1", "done")]


def test_catchall_handler_used_for_unmapped(raising_cls, recording_cls):
    from acq4.experiment.actions.flow import GoToNextAction
    recording_cls.ran.clear()
    handler = Protocol(
        nodes={"h": recording_cls(name="h"), "adv": GoToNextAction(name="adv")},
        edges={("h", "done"): "adv"}, entry="h",
    )
    # raises Fouled; only a catch-all "Exception" handler exists
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "Fouled"})},
        edges={}, entry="a",
        exceptionHandlers={"Exception": handler},
    )
    Orchestrator(p).run_sync_cell("c1")
    assert recording_cls.ran == ["h"]
