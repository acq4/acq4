# Tests for plan data structures and helpers.
from __future__ import annotations

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.planner import MotionPlanner
from acq4.motion.tests.conftest import MockDevice


def _collect(plan):
    return MotionPlanner().collect_devices(plan)


def test_atomic_move_stores_fields():
    dev = MockDevice("d1", (1.0, 2.0, 3.0))
    move = AtomicMove(dev, [1.0, 2.0, 3.0], "fast", "test move")
    assert move.device is dev
    np.testing.assert_array_equal(move.position, [1.0, 2.0, 3.0])
    assert move.speed == "fast"
    assert move.explanation == "test move"


def test_atomic_move_position_is_ndarray():
    dev = MockDevice("d1")
    move = AtomicMove(dev, [0, 0, 0], "slow")
    assert isinstance(move.position, np.ndarray)


def test_sequential_group_stores_steps():
    d = MockDevice("d")
    steps = [AtomicMove(d, [0, 0, 0], "fast"), AtomicMove(d, [1, 0, 0], "slow")]
    group = SequentialGroup(steps, "my seq")
    assert group.steps is steps
    assert group.explanation == "my seq"


def test_parallel_group_stores_steps():
    d = MockDevice("d")
    steps = [AtomicMove(d, [0, 0, 0], "fast")]
    group = ParallelGroup(steps, "my par")
    assert group.steps is steps
    assert group.explanation == "my par"


def test_collect_devices_atomic():
    d = MockDevice("d")
    move = AtomicMove(d, [0, 0, 0], "fast")
    assert _collect(move) == {d}


def test_collect_devices_sequential():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    group = SequentialGroup([AtomicMove(d1, [0, 0, 0], "fast"), AtomicMove(d2, [0, 0, 0], "fast")])
    assert _collect(group) == {d1, d2}


def test_collect_devices_parallel():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    group = ParallelGroup([AtomicMove(d1, [0, 0, 0], "fast"), AtomicMove(d2, [0, 0, 0], "fast")])
    assert _collect(group) == {d1, d2}


def test_collect_devices_nested():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    d3 = MockDevice("d3")
    inner = ParallelGroup([AtomicMove(d2, [0, 0, 0], "fast"), AtomicMove(d3, [0, 0, 0], "fast")])
    outer = SequentialGroup([AtomicMove(d1, [0, 0, 0], "fast"), inner])
    assert _collect(outer) == {d1, d2, d3}


def test_collect_devices_deduplicates():
    d = MockDevice("d")
    group = SequentialGroup([AtomicMove(d, [0, 0, 0], "fast"), AtomicMove(d, [1, 0, 0], "fast")])
    assert _collect(group) == {d}


# ---------------------------------------------------------------------------
# kwargs passthrough — AtomicMove → moveToGlobalNoPlanning
# ---------------------------------------------------------------------------

def test_atomic_move_kwargs_default_empty():
    d = MockDevice("d")
    move = AtomicMove(d, [0, 0, 0], "fast")
    assert move.kwargs == {}


def test_atomic_move_stores_kwargs():
    d = MockDevice("d")
    move = AtomicMove(d, [0, 0, 0], "fast", "test", {"linear": True, "foo": "bar"})
    assert move.kwargs == {"linear": True, "foo": "bar"}


def test_kwargs_reach_device_via_execute_plan():
    """AtomicMove.kwargs must be forwarded as **kwargs to moveToGlobalNoPlanning."""
    from acq4.motion.planner import _execute_plan

    received = {}

    class _DoneMove:
        """Stand-in for the task a real move returns; _execute_plan waits on it."""

        def wait(self):
            return None

    class _KwargDevice(MockDevice):
        def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
            received.update(kwargs)
            return _DoneMove()

    dev = _KwargDevice("kw_dev")
    plan = AtomicMove(dev, [1e-3, 0, 0], "fast", "test", {"linear": True, "custom": 42})
    _execute_plan(plan)

    assert received.get("linear") is True
    assert received.get("custom") == 42


# ---------------------------------------------------------------------------
# throughline propagation — operation name visible inside moveToGlobalNoPlanning
# ---------------------------------------------------------------------------

class _MockLogger:
    """No-op logger for test devices that need one."""
    def debug(self, *a, **kw): pass
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass


def test_sequential_group_explanation_appears_in_throughline():
    """SequentialGroup.explanation must be active in the throughline during child steps."""
    from acq4.motion.planner import _execute_plan
    from gentletask import throughline

    captured = []

    class _DoneMove:
        def wait(self): return None

    class _TraceDevice(MockDevice):
        logger = _MockLogger()
        def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
            captured.append(throughline.collect("name"))
            return _DoneMove()

    dev = _TraceDevice("trace_dev")
    group = SequentialGroup([AtomicMove(dev, [0, 0, 0], "fast", "step")], "my sequence")
    _execute_plan(group)

    assert len(captured) == 1
    assert "my sequence" in captured[0]


def test_parallel_group_explanation_appears_in_throughline():
    """ParallelGroup.explanation must be in the throughline on each child's thread."""
    import threading
    from acq4.motion.planner import _execute_plan
    from gentletask import throughline

    captured = []
    lock = threading.Lock()

    class _DoneMove:
        def wait(self): return None

    class _TraceDevice(MockDevice):
        logger = _MockLogger()
        def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
            with lock:
                captured.append(throughline.collect("name"))
            return _DoneMove()

    dev1 = _TraceDevice("dev1")
    dev2 = _TraceDevice("dev2")
    group = ParallelGroup(
        [AtomicMove(dev1, [0, 0, 0], "fast", "step1"), AtomicMove(dev2, [1, 0, 0], "fast", "step2")],
        "my parallel",
    )
    _execute_plan(group)

    assert len(captured) == 2
    for chain in captured:
        assert "my parallel" in chain


def test_outer_throughline_frame_propagates_to_device():
    """A frame pushed before _execute_plan (as execute(name=...) does) reaches the device."""
    from acq4.motion.planner import _execute_plan
    from gentletask import throughline

    captured = []

    class _DoneMove:
        def wait(self): return None

    class _TraceDevice(MockDevice):
        logger = _MockLogger()
        def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
            captured.append(throughline.collect("name"))
            return _DoneMove()

    dev = _TraceDevice("trace_dev")
    plan = AtomicMove(dev, [0, 0, 0], "fast", "step")
    with throughline(name="top op"):
        _execute_plan(plan)

    assert len(captured) == 1
    assert "top op" in captured[0]


def test_linear_kwarg_flows_through_safe_path():
    """Steps generated from _safe_path must carry linear=True/False in their kwargs."""
    from acq4.motion.default_planner import DefaultMotionPlanner
    from acq4.motion.spec import MoveSpec
    from acq4.motion.tests.conftest import MockPipette

    class _RealPath(DefaultMotionPlanner):
        def _on_path_computed(self, pip, full_path): pass
        def _on_path_error(self, pip, full_path, failed_at): pass

    pip = MockPipette("p", global_pos=(0, 0, 5e-3), approach_depth=0.0)
    planner = _RealPath()

    # Moving from above tissue into tissue — produces APPROACH_WAYPOINT (linear=False)
    # followed by MOVE_TO_DESTINATION (linear=True)
    target = np.array([5e-3, 0, -3e-3])
    plan = planner.plan([MoveSpec(pip, target)])

    from acq4.motion.plan import AtomicMove as AM, SequentialGroup, ParallelGroup

    def _flat(p):
        if isinstance(p, AM): return [p]
        if isinstance(p, (SequentialGroup, ParallelGroup)):
            return [m for s in p.steps for m in _flat(s)]
        return []

    pip_moves = [m for m in _flat(plan) if m.device is pip]
    assert len(pip_moves) == 2
    # approach waypoint (lateral move above surface) — not linear
    assert pip_moves[0].kwargs.get("linear") is False
    # final move into tissue — linear
    assert pip_moves[1].kwargs.get("linear") is True
