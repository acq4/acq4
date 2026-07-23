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
    assert finished[-1] == ("c1", "done")


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


def test_handler_raising_exception_aborts(raising_cls):
    # main raises BrokenPipette; its handler itself raises Fouled -> controlled abort
    handler = Protocol(
        nodes={"h": raising_cls(name="h", params={"exc": "Fouled"})},
        edges={}, entry="h",
    )
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "BrokenPipette"})},
        edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    with pytest.raises(AbortExperiment):
        Orchestrator(p).run_sync_cell("c1")


def test_status_returns_to_running_after_handler_advance(raising_cls, recording_cls):
    # After a handler recovers by advancing, status must not stay stuck on "error".
    from acq4.experiment.actions.flow import GoToNextAction
    handler = Protocol(
        nodes={"h": recording_cls(name="h"), "adv": GoToNextAction(name="adv")},
        edges={("h", "done"): "adv"}, entry="h",
    )
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "BrokenPipette"})},
        edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    statuses = []
    orch = Orchestrator(p)
    orch.sigStatus.connect(statuses.append)
    orch.run_sync_cell("c1")
    assert statuses == ["running", "error", "running"]


def test_retry_cap_exhausts_and_skips():
    # A handler that always retries an always-failing action must not loop forever;
    # after maxRetries it finishes the cell as "retry-exhausted".
    from acq4.experiment.action import Action
    from acq4.experiment.registry import register_action
    from acq4.experiment.exceptions import BrokenPipette
    from acq4.experiment.actions.flow import RetryCellAction

    @register_action(name="AlwaysFails")
    class AlwaysFails(Action):
        outcomes = ("done",)
        calls = {"n": 0}

        def run(self, ctx):
            AlwaysFails.calls["n"] += 1
            raise BrokenPipette("always fails")

    AlwaysFails.calls["n"] = 0
    handler = Protocol(nodes={"r": RetryCellAction(name="r")}, edges={}, entry="r")
    p = Protocol(
        nodes={"a": AlwaysFails(name="a")}, edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    finished = []
    orch = Orchestrator(p, maxRetries=3)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert finished[-1] == ("c1", "retry-exhausted")
    assert AlwaysFails.calls["n"] == 4  # initial attempt + 3 retries, then give up


def test_unexpected_exception_is_surfaced_not_swallowed():
    """A plain (non-OrchestrationError) exception -- an ordinary bug, not an
    exceptional state routed to a handler -- must not vanish silently. It must
    be surfaced via sigStatus/sigCellFinished as an error and abort the run,
    rather than let the loop carry on as though nothing happened."""
    from acq4.experiment.action import Action
    from acq4.experiment.registry import register_action

    @register_action(name="RaisesPlainAttributeError")
    class _RaisesPlainAttributeError(Action):
        outcomes = ("done",)

        def run(self, ctx):
            raise AttributeError("boom: an ordinary bug, not an OrchestrationError")

    p = Protocol(nodes={"a": _RaisesPlainAttributeError(name="a")}, edges={}, entry="a")
    statuses = []
    finished = []
    orch = Orchestrator(p)
    orch.sigStatus.connect(statuses.append)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")

    assert "error" in statuses
    assert finished == [("c1", "error")]


def test_status_returns_to_running_after_handler_retry():
    from acq4.experiment.action import Action
    from acq4.experiment.registry import register_action
    from acq4.experiment.exceptions import BrokenPipette
    from acq4.experiment.actions.flow import RetryCellAction

    @register_action(name="FailOnceStatus")
    class FailOnceStatus(Action):
        outcomes = ("done",)
        calls = {"n": 0}

        def run(self, ctx):
            FailOnceStatus.calls["n"] += 1
            if FailOnceStatus.calls["n"] == 1:
                raise BrokenPipette("first attempt fails")
            return "done"

    FailOnceStatus.calls["n"] = 0
    handler = Protocol(nodes={"r": RetryCellAction(name="r")}, edges={}, entry="r")
    p = Protocol(
        nodes={"a": FailOnceStatus(name="a")}, edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    statuses = []
    orch = Orchestrator(p)
    orch.sigStatus.connect(statuses.append)
    orch.run_sync_cell("c1")
    # error is emitted during handling, then running is re-emitted for the retry
    # attempt (status must NOT stay stuck on "error")
    assert statuses == ["running", "error", "running"]
