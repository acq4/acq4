# Tests for MinirigV1MotionPlanner — scope-park / scope-unwind behaviour.
from __future__ import annotations

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import MockDevice, MockInteractionSite, MockPipette, MockScope


def make_planner():
    from acq4.motion.minirig_v1 import MinirigV1MotionPlanner
    return MinirigV1MotionPlanner()


def _flat_moves(plan):
    if isinstance(plan, AtomicMove):
        return [plan]
    if isinstance(plan, (SequentialGroup, ParallelGroup)):
        result = []
        for step in plan.steps:
            result.extend(_flat_moves(step))
        return result
    return []


# ---------------------------------------------------------------------------
# Interaction approach with scope park
# ---------------------------------------------------------------------------

def test_no_scope_park_when_not_configured(pip, site):
    """Sites without scopeParkPos produce no scope moves."""
    plan = make_planner().plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site)])
    assert not any(isinstance(m.device, MockScope) for m in _flat_moves(plan))


def test_scope_park_prepended_when_configured(pip, site_with_scope_park):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site_with_scope_park)])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    pip_moves = [m for m in moves if m.device is pip]

    assert len(scope_moves) >= 1
    assert moves.index(scope_moves[0]) < moves.index(pip_moves[0])


def test_scope_park_populates_context(pip, site_with_scope_park):
    planner = make_planner()
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site_with_scope_park)])
    assert pip.name() in planner._scope_context


def test_scope_park_not_repeated_if_already_parked(pip, site_with_scope_park):
    """If _scope_context is already populated, the approach plan must not re-park."""
    planner = make_planner()
    scope = pip.scopeDevice()
    planner._scope_context[pip.name()] = (scope, [np.zeros(3), np.zeros(3), np.zeros(3)])

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flat_moves(plan) if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


# ---------------------------------------------------------------------------
# Scope unwind on return home
# ---------------------------------------------------------------------------

def _seed_scope_context(planner, pip):
    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    planner._scope_context[pip.name()] = (scope, [original_pos, up_pos, park_pos])
    return scope, original_pos, up_pos, park_pos


def test_scope_unwind_appended_after_pip_home(pip):
    planner = make_planner()
    scope, *_ = _seed_scope_context(planner, pip)

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    moves = _flat_moves(plan)

    scope_moves = [m for m in moves if m.device is scope]
    pip_moves = [m for m in moves if m.device is pip]

    assert len(scope_moves) >= 1
    assert moves.index(scope_moves[0]) > moves.index(pip_moves[-1])


def test_scope_unwind_reverses_park_path(pip):
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)

    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    # re-plan to verify what was generated (context is cleared after planning)
    planner._scope_context[pip.name()] = (scope, [original_pos, up_pos, park_pos])
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if m.device is scope]

    assert len(scope_moves) == 2
    np.testing.assert_array_almost_equal(scope_moves[0].position, up_pos)
    np.testing.assert_array_almost_equal(scope_moves[1].position, original_pos)


def test_scope_context_cleared_after_plan(pip):
    planner = make_planner()
    _seed_scope_context(planner, pip)
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    assert pip.name() not in planner._scope_context


def test_no_scope_unwind_when_context_empty(pip):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    assert not any(isinstance(m.device, MockScope) for m in _flat_moves(plan))
