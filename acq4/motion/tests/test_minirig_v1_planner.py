# Tests for MinirigV1MotionPlanner — scope-park / scope-unwind behaviour.
from __future__ import annotations

import numpy as np

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import MockPipette, MockScope


def make_planner():
    from acq4.motion.minirig_v1 import MinirigV1MotionPlanner

    class _TestPlanner(MinirigV1MotionPlanner):
        def _safe_path(self, pip, globalStart, globalStop, speed, explanation=None):
            return [(np.asarray(globalStop, dtype=float), speed, False, explanation or "move")]

    return _TestPlanner()


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
# Interaction approach with microscope park
# ---------------------------------------------------------------------------


def test_no_scope_park_when_not_configured(pip, site):
    """Sites without scopeParkPos produce no scope moves."""
    plan = make_planner().plan([MoveSpec(pip, np.zeros(3), relative_to=site)])
    assert not any(isinstance(m.device, MockScope) for m in _flat_moves(plan))


def test_scope_park_prepended_when_configured(pip, site_with_scope_park):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    pip_moves = [m for m in moves if m.device is pip]

    assert len(scope_moves) >= 1
    assert moves.index(scope_moves[0]) < moves.index(pip_moves[0])


def test_scope_park_populates_context(pip, site_with_scope_park):
    planner = make_planner()
    planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])
    assert pip.name() in planner._scope_context


def test_scope_park_not_repeated_if_already_parked(pip, site_with_scope_park):
    """If _scope_context is already populated, the approach plan must not re-park."""
    planner = make_planner()
    scope = pip.scopeDevice()
    planner._scope_context[pip.name()] = (scope, [np.zeros(3), np.zeros(3), np.zeros(3)])

    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flat_moves(plan) if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


# ---------------------------------------------------------------------------
# Scope unwind on return home (via _plan_pipette_move fallback)
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

    # re-seed and re-plan to inspect the generated scope moves
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


# ---------------------------------------------------------------------------
# Scope-up-first sequence for approach with scopeParkPos
# ---------------------------------------------------------------------------


def test_scope_up_is_first_move_in_approach(pip, site_with_scope_park):
    """Scope must move up (z-only) as the very first step, before any pip or lateral scope move."""
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])
    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    assert moves[0].device is pip.scopeDevice(), "First move must be scope up"
    park_pos = site_with_scope_park.config["scopeParkPos"]
    up_pos = np.array(
        [pip.scopeDevice().globalPosition()[0], pip.scopeDevice().globalPosition()[1], park_pos[2]]
    )
    np.testing.assert_array_almost_equal(
        moves[0].position, up_pos, err_msg="First scope move must be z-only (up to park height)"
    )


def test_pip_retract_before_scope_lateral_when_pip_in_tissue(site_with_scope_park):
    """When pip starts below approach depth, it must retract before scope moves laterally."""
    pip_below = MockPipette("pip_below", global_pos=(0.0, 0.0, -3e-3), approach_depth=0.0)
    site_with_scope_park.save_positions_for(pip_below, np.array([0.0, 0.0, -1e-3]))
    site_with_scope_park.save_approach_for(pip_below)

    planner = make_planner()
    plan = planner.plan([MoveSpec(pip_below, np.zeros(3), relative_to=site_with_scope_park)])
    moves = _flat_moves(plan)

    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    pip_moves = [m for m in moves if m.device is pip_below]
    all_idxs = {id(m): i for i, m in enumerate(moves)}

    # scope up is first
    assert all_idxs[id(scope_moves[0])] == 0, "Scope up must be first"

    # pip retract (any pip move) comes before the second scope move (park lateral)
    assert len(scope_moves) >= 2, "Expected scope up + scope lateral moves"
    first_pip_idx = all_idxs[id(pip_moves[0])]
    scope_lateral_idx = all_idxs[id(scope_moves[1])]
    assert (
        first_pip_idx < scope_lateral_idx
    ), "Pip retract must come before scope lateral move to park position"


def test_pip_no_retract_step_when_already_at_safe_height(site_with_scope_park):
    """When pip is already at approach depth, no pip retract step is prepended."""
    pip_safe = MockPipette("pip_safe", global_pos=(0.0, 0.0, 0.0), approach_depth=0.0)
    site_with_scope_park.save_positions_for(pip_safe, np.array([0.0, 0.0, -1e-3]))
    site_with_scope_park.save_approach_for(pip_safe)

    planner = make_planner()
    plan = planner.plan([MoveSpec(pip_safe, np.zeros(3), relative_to=site_with_scope_park)])
    moves = _flat_moves(plan)

    # scope up, scope lateral, then pip — no pip move between scope up and scope lateral
    scope_idxs = [i for i, m in enumerate(moves) if isinstance(m.device, MockScope)]
    pip_idxs = [i for i, m in enumerate(moves) if m.device is pip_safe]
    assert len(scope_idxs) >= 2
    # no pip move should appear between scope up (scope_idxs[0]) and scope lateral (scope_idxs[1])
    between = [i for i in pip_idxs if scope_idxs[0] < i < scope_idxs[1]]
    assert len(between) == 0, "No pip move should appear between scope-up and scope-lateral"


# ---------------------------------------------------------------------------
# Scope unwind via interaction exit (_plan_interaction_exit path)
# ---------------------------------------------------------------------------


def test_scope_unwind_appended_after_interaction_exit(pip, site_with_scope_park):
    """When pip exits a site via _plan_interaction_exit, scope unwind is still appended."""
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)
    approach_global = np.array(site_with_scope_park.globalPosition())
    planner._find_containing_site = lambda dev: site_with_scope_park if dev is pip else None

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    moves = _flat_moves(plan)

    scope_moves = [m for m in moves if m.device is scope]
    pip_moves = [m for m in moves if m.device is pip]

    # first pip move is exit-to-approach
    np.testing.assert_array_almost_equal(pip_moves[0].position, approach_global)
    # scope unwind follows all pip moves
    assert len(scope_moves) >= 1
    last_pip_idx = max(i for i, m in enumerate(moves) if m.device is pip)
    first_scope_idx = min(i for i, m in enumerate(moves) if m.device is scope)
    assert first_scope_idx > last_pip_idx
