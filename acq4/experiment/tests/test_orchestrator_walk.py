"""Tests for the Orchestrator graph walk and outcome routing (single cell)."""
import pytest

from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator


def test_walk_straight_line(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")       # returns "done"
    b = recording_cls(name="b")       # returns "done"
    p = Protocol(nodes={"a": a, "b": b},
                 edges={("a", "done"): "b"}, entry="a")
    Orchestrator(p).run_sync_cell("cell1")
    assert recording_cls.ran == ["a", "b"]


def test_walk_branches_on_outcome(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a", params={"next": "left"})   # returns "left"
    left = recording_cls(name="left")
    right = recording_cls(name="right")
    p = Protocol(nodes={"a": a, "left": left, "right": right},
                 edges={("a", "left"): "left", ("a", "right"): "right"},
                 entry="a")
    Orchestrator(p).run_sync_cell("cell1")
    assert recording_cls.ran == ["a", "left"]


def test_unknown_outcome_raises(recording_cls):
    a = recording_cls(name="a", params={"next": "bogus-not-in-outcomes"})
    # 'bogus-not-in-outcomes' is not in RecordingAction.outcomes
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    with pytest.raises(ValueError):
        Orchestrator(p).run_sync_cell("cell1")


def test_current_action_signal_emitted(qtbot, recording_cls):
    a = recording_cls(name="a")
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    orch = Orchestrator(p)
    with qtbot.waitSignal(orch.sigCurrentAction, timeout=1000) as blocker:
        orch.run_sync_cell("cell1")
    assert blocker.args[0] == "cell1"
    assert blocker.args[1] is a
