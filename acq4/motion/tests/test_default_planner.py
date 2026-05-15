# Tests for DefaultMotionPlanner.plan().
# The default planner is rig-agnostic: no scope parking, no unwind logic.
from __future__ import annotations

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.planner import PlanningError
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import MockDevice, MockInteractionSite, MockPipette, MockScope


def make_planner():
    from acq4.motion.default_planner import DefaultMotionPlanner
    return DefaultMotionPlanner()


def _flat_moves(plan):
    """Flatten a plan tree into a list of AtomicMove objects in execution order."""
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
    assert _flat_moves(plan)[0].speed == "slow"


def test_generic_device_default_speed_is_fast():
    planner = make_planner()
    dev = MockDevice("dev1")
    plan = planner.plan([MoveSpec(dev, [0, 0, 0])])
    assert _flat_moves(plan)[0].speed == "fast"


def test_generic_device_relative_to_resolves_to_global():
    planner = make_planner()
    dev = MockDevice("dev1")
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    local_pos = np.array([1e-3, 0.0, 0.0])
    plan = planner.plan([MoveSpec(dev, local_pos, relative_to=anchor)])
    np.testing.assert_array_almost_equal(_flat_moves(plan)[0].position, [11e-3, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Pipette safe-path moves
# ---------------------------------------------------------------------------

def test_pipette_move_produces_atomic_steps(pip):
    planner = make_planner()
    target = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, target)])
    moves = _flat_moves(plan)
    assert all(isinstance(m, AtomicMove) for m in moves)
    assert moves[-1].device is pip
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_move_retraction_when_near_sample(pip):
    retract_pos = np.array([0.0, 0.0, 0.0])
    target = np.array([1e-3, 0.0, -0.5e-3])

    pip.pathGenerator.safePath.side_effect = lambda start, stop, speed, explanation=None: [
        (retract_pos, "slow", True, "retraction"),
        (np.asarray(stop, dtype=float), speed, False, "final"),
    ]

    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, target)])
    moves = _flat_moves(plan)
    np.testing.assert_array_almost_equal(moves[0].position, retract_pos)
    assert moves[0].speed == "slow"
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_speed_hint_propagated(pip):
    captured = []

    def capture(start, stop, speed, explanation=None):
        captured.append(speed)
        return [(np.asarray(stop, dtype=float), speed, False, "move")]

    pip.pathGenerator.safePath.side_effect = capture
    make_planner().plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]), speed="slow")])
    assert captured[0] == "slow"


def test_pipette_uses_pip_path_generator(pip):
    """Planner must use pip.pathGenerator, not a freshly constructed PipettePathGenerator."""
    planner = make_planner()
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    assert pip.pathGenerator.safePath.called


# ---------------------------------------------------------------------------
# InteractionSite approach — approach = site origin
# ---------------------------------------------------------------------------

def test_interaction_approach_only_goes_to_site_origin(pip, site):
    """MoveSpec with zero position = approach only; pip ends at site.globalPosition()."""
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site)])
    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]
    np.testing.assert_array_almost_equal(pip_moves[-1].position, site.globalPosition())


def test_interaction_site_plan_has_approach_then_interact(pip, site):
    """Non-zero spec.position goes to approach first, then to the target inside the site."""
    planner = make_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site)])

    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]

    approach_global = np.array(site.globalPosition())
    interact_global = np.array(site.positions[pip.name()]["interact global"])

    approach_idx = next(
        i for i, m in enumerate(pip_moves)
        if np.allclose(m.position, approach_global, atol=1e-9)
    )
    interact_idx = next(
        i for i, m in enumerate(pip_moves)
        if np.allclose(m.position, interact_global, atol=1e-9)
    )
    assert approach_idx < interact_idx


def test_direct_access_site_skips_approach_waypoint(pip, site_with_direct_access):
    """Sites with directAccess: true skip the approach waypoint enforcement."""
    planner = make_planner()
    interact_local = np.array(site_with_direct_access.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site_with_direct_access)])
    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]
    approach_global = np.array(site_with_direct_access.globalPosition())
    interact_global = np.array(site_with_direct_access.positions[pip.name()]["interact global"])
    # last move reaches the interact position
    np.testing.assert_array_almost_equal(pip_moves[-1].position, interact_global)
    # approach position must not appear as an intermediate stop
    assert not any(
        np.allclose(m.position, approach_global) for m in pip_moves[:-1]
    )


def test_interaction_site_no_scope_moves_in_default_planner(pip, site_with_scope_park):
    """DefaultMotionPlanner never touches the scope, even when scopeParkPos is configured."""
    planner = make_planner()
    interact_local = np.array(site_with_scope_park.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flat_moves(plan) if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


# ---------------------------------------------------------------------------
# InteractionSite exit — approach waypoint prepended when pip is inside a site
# ---------------------------------------------------------------------------

def test_interaction_exit_prepends_approach_waypoint(pip, site):
    """When _find_containing_site returns a site, the pip exits via approach first."""
    planner = make_planner()
    planner._find_containing_site = lambda dev: site if dev is pip else None

    home_pos = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, home_pos)])
    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]

    np.testing.assert_array_almost_equal(pip_moves[0].position, site.globalPosition())
    np.testing.assert_array_almost_equal(pip_moves[-1].position, home_pos)


def test_no_exit_waypoint_when_pip_not_in_site(pip):
    """When _find_containing_site returns None, no approach waypoint is added."""
    planner = make_planner()
    planner._find_containing_site = lambda dev: None

    home_pos = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, home_pos)])
    moves = _flat_moves(plan)
    pip_moves = [m for m in moves if m.device is pip]

    np.testing.assert_array_almost_equal(pip_moves[0].position, home_pos)


# ---------------------------------------------------------------------------
# collect_devices
# ---------------------------------------------------------------------------

def test_collect_devices_includes_scope_for_pipette(pip):
    """DefaultMotionPlanner adds the pipette's scope to the reserved device set."""
    planner = make_planner()
    plan = SequentialGroup([AtomicMove(pip, np.zeros(3), "fast")])
    devices = planner.collect_devices(plan)
    assert pip in devices
    assert pip.scopeDevice() in devices


def test_collect_devices_generic_device_no_extra(pip):
    dev = MockDevice("dev1")
    planner = make_planner()
    plan = SequentialGroup([AtomicMove(dev, np.zeros(3), "fast")])
    devices = planner.collect_devices(plan)
    assert devices == {dev}


# ---------------------------------------------------------------------------
# Move name propagation
# ---------------------------------------------------------------------------

def test_plan_name_becomes_top_level_explanation(pip):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3))], name="go home")
    assert plan.explanation == "go home"


def test_plan_default_explanation_when_no_name(pip):
    planner = make_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3))])
    assert plan.explanation == "motion plan"
