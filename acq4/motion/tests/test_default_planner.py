# Tests for DefaultMotionPlanner.plan().
# All tests are purely structural — no hardware is commanded.
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.planner import PlanningError
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import MockDevice, MockInteractionSite, MockPipette, MockScope


def make_planner():
    from acq4.motion.default_planner import DefaultMotionPlanner
    return DefaultMotionPlanner()


def _flat_moves(plan):
    """Flatten a plan tree into a list of AtomicMove objects (in execution order)."""
    if isinstance(plan, AtomicMove):
        return [plan]
    if isinstance(plan, (SequentialGroup, ParallelGroup)):
        result = []
        for step in plan.steps:
            result.extend(_flat_moves(step))
        return result
    return []


# ---------------------------------------------------------------------------
# Generic device move
# ---------------------------------------------------------------------------

def test_generic_device_global_move():
    planner = make_planner()
    dev = MockDevice("dev1", (0.0, 0.0, 0.0))
    target = np.array([1e-3, 2e-3, 3e-3])
    plan = planner.plan([MoveSpec(dev, target)])
    moves = _flat_moves(plan)
    assert len(moves) == 1
    assert moves[0].device is dev
    np.testing.assert_array_almost_equal(moves[0].position, target)


def test_generic_device_speed_hint_used():
    planner = make_planner()
    dev = MockDevice("dev1")
    plan = planner.plan([MoveSpec(dev, [0, 0, 0], speed="slow")])
    moves = _flat_moves(plan)
    assert moves[0].speed == "slow"


def test_generic_device_default_speed_is_fast():
    planner = make_planner()
    dev = MockDevice("dev1")
    plan = planner.plan([MoveSpec(dev, [0, 0, 0])])
    moves = _flat_moves(plan)
    assert moves[0].speed == "fast"


def test_generic_device_relative_to_resolves_to_global():
    planner = make_planner()
    dev = MockDevice("dev1")
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    local_pos = np.array([1e-3, 0.0, 0.0])
    plan = planner.plan([MoveSpec(dev, local_pos, relative_to=anchor)])
    moves = _flat_moves(plan)
    # global = anchor.mapToGlobal(local_pos) = anchor_pos + local_pos = [11e-3, 0, 0]
    np.testing.assert_array_almost_equal(moves[0].position, [11e-3, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Pipette safe-path moves (PipettePathGenerator mocked)
# ---------------------------------------------------------------------------

def _make_simple_safepath(start, stop, speed, explanation=None):
    """Return a simple one-step path (no waypoints) for testing."""
    return [(np.asarray(stop), speed, False, explanation or "move")]


def test_pipette_move_produces_atomic_steps(pip):
    planner = make_planner()
    target = np.array([0.0, 0.0, 5e-3])
    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=_make_simple_safepath,
    ):
        plan = planner.plan([MoveSpec(pip, target)])
    moves = _flat_moves(plan)
    assert all(isinstance(m, AtomicMove) for m in moves)
    assert moves[-1].device is pip
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_move_retraction_when_near_sample():
    """safePath is called; planner trusts it to insert retraction waypoints."""
    planner = make_planner()
    pip = MockPipette("pip1", global_pos=(0.0, 0.0, -0.5e-3), approach_depth=0.0)
    target = np.array([1e-3, 0.0, -0.5e-3])

    retract_pos = np.array([0.0, 0.0, 0.0])

    def safepath_with_retract(start, stop, speed, explanation=None):
        return [
            (retract_pos, "slow", True, "retraction"),
            (stop, speed, False, "final"),
        ]

    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=safepath_with_retract,
    ):
        plan = planner.plan([MoveSpec(pip, target)])

    moves = _flat_moves(plan)
    np.testing.assert_array_almost_equal(moves[0].position, retract_pos)
    assert moves[0].speed == "slow"
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_speed_hint_propagated(pip):
    planner = make_planner()
    target = np.array([0.0, 0.0, 5e-3])
    captured = []

    def capture_safepath(start, stop, speed, explanation=None):
        captured.append(speed)
        return [(stop, speed, False, "move")]

    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=capture_safepath,
    ):
        planner.plan([MoveSpec(pip, target, speed="slow")])

    assert captured[0] == "slow"


# ---------------------------------------------------------------------------
# InteractionSite approach
# ---------------------------------------------------------------------------

def test_interaction_site_plan_has_approach_then_interact(pip, site):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site)])

    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]
    assert len(pip_moves) >= 2

    approach_global = np.array(site.positions[pip.name()]["site global"])
    interact_global = np.array(site.positions[pip.name()]["interact global"])

    # approach before interact
    approach_idx = next(
        i for i, m in enumerate(pip_moves)
        if np.allclose(m.position, approach_global, atol=1e-9)
    )
    interact_idx = next(
        i for i, m in enumerate(pip_moves)
        if np.allclose(m.position, interact_global, atol=1e-9)
    )
    assert approach_idx < interact_idx


def test_interaction_site_no_scope_park_when_not_configured(pip, site):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site)])
    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


def test_interaction_site_scope_park_prepended(pip, site_with_scope_park):
    planner = make_planner()
    site = site_with_scope_park
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site)])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if isinstance(m.device, MockScope)]
    pip_moves = [m for m in moves if m.device is pip]

    # scope must move before pip
    assert len(scope_moves) >= 1
    first_scope_idx = moves.index(scope_moves[0])
    first_pip_idx = moves.index(pip_moves[0])
    assert first_scope_idx < first_pip_idx


def test_interaction_site_scope_park_populates_context(pip, site_with_scope_park):
    planner = make_planner()
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=site_with_scope_park)])
    assert pip.name() in planner._scope_context


def test_interaction_site_missing_positions_raises(pip):
    planner = make_planner()
    empty_site = MockInteractionSite("empty", global_pos=(5e-3, 0.0, 0.0))
    with pytest.raises(PlanningError):
        planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 0.0]), relative_to=empty_site)])


# ---------------------------------------------------------------------------
# Scope unwind on return home
# ---------------------------------------------------------------------------

def test_scope_unwind_appended_when_context_set(pip, site_with_scope_park):
    planner = make_planner()

    # seed the scope context as if we already did the approach
    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    planner._scope_context[pip.name()] = (scope, [original_pos, up_pos, park_pos])

    target = np.array([0.0, 0.0, 5e-3])
    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=_make_simple_safepath,
    ):
        plan = planner.plan([MoveSpec(pip, target)])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if m.device is scope]
    pip_moves = [m for m in moves if m.device is pip]

    # scope must move AFTER pip reaches home
    assert len(scope_moves) >= 1
    last_pip_idx = moves.index(pip_moves[-1])
    first_scope_unwind_idx = moves.index(scope_moves[0])
    assert first_scope_unwind_idx > last_pip_idx


def test_scope_unwind_reverses_park_path(pip, site_with_scope_park):
    planner = make_planner()

    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    planner._scope_context[pip.name()] = (scope, [original_pos, up_pos, park_pos])

    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=_make_simple_safepath,
    ):
        plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if m.device is scope]

    # return path should be reverse of forward (excluding start): [park→up→original]
    assert len(scope_moves) == 2
    np.testing.assert_array_almost_equal(scope_moves[0].position, up_pos)
    np.testing.assert_array_almost_equal(scope_moves[1].position, original_pos)


def test_scope_context_cleared_after_return(pip):
    planner = make_planner()
    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    planner._scope_context[pip.name()] = (scope, [original_pos, up_pos, park_pos])

    with patch(
        "acq4.motion.default_planner.PipettePathGenerator.safePath",
        side_effect=_make_simple_safepath,
    ):
        planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    assert pip.name() not in planner._scope_context
