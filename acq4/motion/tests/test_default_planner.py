# Tests for DefaultMotionPlanner.plan().
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.planner import PlanningError
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import (
    MockDevice,
    MockInteractionSite,
    MockInteractionSiteArray,
    MockPipette,
    MockScope,
    MockStage,
)


class _FakeManager:
    """Minimal Manager stand-in for _find_containing_site: a name->device registry."""

    def __init__(self, devices):
        self._devices = {d.name(): d for d in devices}

    def listDevices(self):
        return list(self._devices)

    def getDevice(self, name):
        return self._devices[name]


def make_simplified_planner():
    """Return a DefaultMotionPlanner whose _safe_path returns a straight line to the target."""
    from acq4.motion.default_planner import DefaultMotionPlanner

    class _TestPlanner(DefaultMotionPlanner):
        def _safe_path(self, pip, globalStart, globalStop, speed, explanation=None):
            return [(np.asarray(globalStop, dtype=float), speed, False, explanation or "move")]

    return _TestPlanner()


def make_real_planner():
    """Return a DefaultMotionPlanner that runs the real _safe_path without Visualize3D side-effects."""
    from acq4.motion.default_planner import DefaultMotionPlanner

    class _RealPathPlanner(DefaultMotionPlanner):
        def _on_path_computed(self, pip, full_path):
            pass

        def _on_path_error(self, pip, full_path, failed_at):
            pass

    return _RealPathPlanner()


def _flatten(plan):
    """Flatten a plan tree into a list of AtomicMove objects in execution order."""
    if isinstance(plan, AtomicMove):
        return [plan]
    if isinstance(plan, (SequentialGroup, ParallelGroup)):
        result = []
        for step in plan.steps:
            result.extend(_flatten(step))
        return result
    return []


def _collect_parallel_groups(plan):
    """Walk the plan tree and return all ParallelGroup nodes."""
    if isinstance(plan, ParallelGroup):
        return [plan] + [pg for step in plan.steps for pg in _collect_parallel_groups(step)]
    if isinstance(plan, SequentialGroup):
        return [pg for step in plan.steps for pg in _collect_parallel_groups(step)]
    return []


# ---------------------------------------------------------------------------
# Generic device move
# ---------------------------------------------------------------------------

def test_generic_device_global_move():
    planner = make_simplified_planner()
    dev = MockDevice("dev1", (0.0, 0.0, 0.0))
    target = np.array([1e-3, 2e-3, 3e-3])
    plan = planner.plan([MoveSpec(dev, target)])
    moves = _flatten(plan)
    assert len(moves) == 1
    assert moves[0].device is dev
    np.testing.assert_array_almost_equal(moves[0].position, target)


def test_generic_device_speed_hint_used():
    planner = make_simplified_planner()
    dev = MockDevice("dev1")
    plan = planner.plan([MoveSpec(dev, [0, 0, 0], speed="slow")])
    assert _flatten(plan)[0].speed == "slow"


def test_generic_device_default_speed_is_fast():
    planner = make_simplified_planner()
    dev = MockDevice("dev1")
    plan = planner.plan([MoveSpec(dev, [0, 0, 0])])
    assert _flatten(plan)[0].speed == "fast"


def test_generic_device_relative_to_resolves_to_global():
    planner = make_simplified_planner()
    dev = MockDevice("dev1")
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    local_pos = np.array([1e-3, 0.0, 0.0])
    plan = planner.plan([MoveSpec(dev, local_pos, relative_to=anchor)])
    np.testing.assert_array_almost_equal(_flatten(plan)[0].position, [11e-3, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Pipette safe-path moves
# ---------------------------------------------------------------------------

def test_pipette_move_produces_atomic_steps(pip):
    planner = make_simplified_planner()
    target = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, target)])
    moves = _flatten(plan)
    assert all(isinstance(m, AtomicMove) for m in moves)
    assert moves[-1].device is pip
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_move_retraction_when_near_sample(pip):
    retract_pos = np.array([0.0, 0.0, 0.0])
    target = np.array([1e-3, 0.0, -0.5e-3])

    planner = make_simplified_planner()
    planner._safe_path = lambda p, start, stop, speed, explanation=None: [
        (retract_pos, "slow", True, "retraction"),
        (np.asarray(stop, dtype=float), speed, False, "final"),
    ]

    plan = planner.plan([MoveSpec(pip, target)])
    moves = _flatten(plan)
    np.testing.assert_array_almost_equal(moves[0].position, retract_pos)
    assert moves[0].speed == "slow"
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_pipette_speed_hint_propagated(pip):
    captured = []

    planner = make_simplified_planner()
    original = planner._safe_path

    def capture(p, start, stop, speed, explanation=None):
        captured.append(speed)
        return original(p, start, stop, speed, explanation)

    planner._safe_path = capture
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]), speed="slow")])
    assert captured[0] == "slow"


def test_pipette_uses_planner_safe_path(pip):
    """Planner must route pipette moves through its own _safe_path."""
    planner = make_simplified_planner()
    called = []
    original = planner._safe_path
    planner._safe_path = lambda *a, **kw: called.append(True) or original(*a, **kw)
    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    assert called


# ---------------------------------------------------------------------------
# InteractionSite approach — approach = site origin
# ---------------------------------------------------------------------------

def test_interaction_approach_only_goes_to_site_origin(pip, site):
    """MoveSpec with zero position = approach only; pip ends at site.globalPosition()."""
    planner = make_simplified_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]
    np.testing.assert_array_almost_equal(pip_moves[-1].position, site.globalPosition())


def test_interaction_site_plan_has_approach_then_interact(pip, site):
    """Non-zero spec.position goes to approach first, then to the target inside the site."""
    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site)])

    moves = _flatten(plan)
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


def test_non_strict_path_site_skips_approach_waypoint(pip, site_without_strict_path):
    """Sites without a saved approach position skip the approach waypoint on entry."""
    planner = make_simplified_planner()
    interact_local = np.array(site_without_strict_path.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site_without_strict_path)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]
    approach_global = np.array(site_without_strict_path.globalPosition())
    interact_global = np.array(site_without_strict_path.positions[pip.name()]["interact global"])
    # last move reaches the interact position
    np.testing.assert_array_almost_equal(pip_moves[-1].position, interact_global)
    # approach position must not appear as an intermediate stop
    assert not any(
        np.allclose(m.position, approach_global) for m in pip_moves[:-1]
    )


def test_movable_site_stage_repositioned_before_approach(pip):
    """If approachMoveSpec returns a spec, the stage is moved in parallel with pip rising."""
    from acq4.motion.spec import MoveSpec as _MoveSpec
    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    # Site is currently at (6e-3, 0, -2e-3) — stage has drifted from calibrated position.
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    # Calibrated approach position is (5e-3, 0, -2e-3) — where it should be.
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.save_approach_for(pip, calibrated_approach)

    stage_target = np.array([2e-3, 0.0, 0.0])  # stage must move 1mm left
    site.approachMoveSpec = lambda p, speed='fast': _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])
    moves = _flatten(plan)

    stage_moves = [m for m in moves if m.device is stage]
    pip_moves = [m for m in moves if m.device is pip]

    assert len(stage_moves) >= 1
    first_stage_idx = min(i for i, m in enumerate(moves) if m.device is stage)
    first_pip_approach_idx = min(
        i for i, m in enumerate(moves)
        if m.device is pip and np.allclose(m.position, calibrated_approach, atol=1e-9)
    )
    assert first_stage_idx < first_pip_approach_idx
    # final pip move is the interact position corrected for site movement (delta = -1e-3 in x)
    expected_interact = interact_global + (calibrated_approach - np.array([6e-3, 0.0, -2e-3]))
    np.testing.assert_array_almost_equal(pip_moves[-1].position, expected_interact)


def test_fixed_site_no_stage_move(pip, site):
    """Fixed sites (approachMoveSpec returns None) produce no stage move."""
    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site)])
    moves = _flatten(plan)
    stage_moves = [m for m in moves if isinstance(m.device, MockStage)]
    assert len(stage_moves) == 0


def test_interaction_site_no_scope_moves_in_default_planner(pip, site_with_scope_park):
    """DefaultMotionPlanner never touches the scope, even when scopeParkPos is configured."""
    planner = make_simplified_planner()
    interact_local = np.array(site_with_scope_park.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flatten(plan) if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


# ---------------------------------------------------------------------------
# InteractionSite exit — approach waypoint prepended only for strict-path sites
# ---------------------------------------------------------------------------

def test_interaction_exit_prepends_approach_waypoint(pip, site):
    """When _find_containing_site returns a site, the pip exits via approach first."""
    planner = make_simplified_planner()
    planner._find_containing_site = lambda dev: site if dev is pip else None

    home_pos = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, home_pos)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]

    np.testing.assert_array_almost_equal(pip_moves[0].position, site.globalPosition())
    np.testing.assert_array_almost_equal(pip_moves[-1].position, home_pos)


def test_no_exit_waypoint_when_pip_not_in_site(pip):
    """When _find_containing_site returns None, no approach waypoint is added."""
    planner = make_simplified_planner()
    planner._find_containing_site = lambda dev: None

    home_pos = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, home_pos)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]

    np.testing.assert_array_almost_equal(pip_moves[0].position, home_pos)


def test_non_strict_exit_skips_approach_waypoint(pip, site_without_strict_path):
    """Sites without a saved approach position allow the pip to exit directly."""
    planner = make_simplified_planner()
    planner._find_containing_site = lambda dev: site_without_strict_path if dev is pip else None

    home_pos = np.array([0.0, 0.0, 5e-3])
    plan = planner.plan([MoveSpec(pip, home_pos)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]

    approach_global = np.array(site_without_strict_path.globalPosition())
    assert not any(np.allclose(m.position, approach_global) for m in pip_moves)
    np.testing.assert_array_almost_equal(pip_moves[-1].position, home_pos)


# ---------------------------------------------------------------------------
# _find_containing_site / _is_interaction_site — InteractionSiteArray must not
# be mistaken for a single site (it manages child sites and has no containsPoint)
# ---------------------------------------------------------------------------

def test_is_interaction_site_true_for_single_site(site):
    """A single InteractionSite (with containsPoint) is an interaction site."""
    planner = make_simplified_planner()
    assert planner._is_interaction_site(site) is True


def test_is_interaction_site_false_for_site_array():
    """An InteractionSiteArray container is not itself an interaction site."""
    planner = make_simplified_planner()
    array = MockInteractionSiteArray("nucleus_array")
    assert planner._is_interaction_site(array) is False


def test_find_containing_site_ignores_site_array(pip, monkeypatch):
    """An InteractionSiteArray in the device list must be skipped, not have containsPoint
    called on it (it has none). The real child site is returned instead."""
    import acq4.motion.default_planner as dp

    site = MockInteractionSite("cleanwell", global_pos=(0.0, 0.0, 0.0))  # contains pip at origin
    array = MockInteractionSiteArray("nucleus_array", sites=[site])
    monkeypatch.setattr(dp, "getManager", lambda: _FakeManager([array, site]))

    planner = make_simplified_planner()
    assert planner._find_containing_site(pip) is site


def test_find_containing_site_returns_none_when_pip_outside(pip, monkeypatch):
    """No site contains the pip → None (and the array is still skipped without error)."""
    import acq4.motion.default_planner as dp

    far_site = MockInteractionSite("cleanwell", global_pos=(50e-3, 0.0, 0.0))
    array = MockInteractionSiteArray("nucleus_array", sites=[far_site])
    monkeypatch.setattr(dp, "getManager", lambda: _FakeManager([array, far_site]))

    planner = make_simplified_planner()
    assert planner._find_containing_site(pip) is None


# ---------------------------------------------------------------------------
# collect_devices
# ---------------------------------------------------------------------------

def test_collect_devices_includes_scope_for_pipette(pip):
    """DefaultMotionPlanner adds the pipette's scope to the reserved device set."""
    planner = make_simplified_planner()
    plan = SequentialGroup([AtomicMove(pip, np.zeros(3), "fast")])
    devices = planner.collect_devices(plan)
    assert pip in devices
    assert pip.scopeDevice() in devices


def test_collect_devices_generic_device_no_extra(pip):
    dev = MockDevice("dev1")
    planner = make_simplified_planner()
    plan = SequentialGroup([AtomicMove(dev, np.zeros(3), "fast")])
    devices = planner.collect_devices(plan)
    assert devices == {dev}


# ---------------------------------------------------------------------------
# Move name propagation
# ---------------------------------------------------------------------------

def test_plan_name_becomes_top_level_explanation(pip):
    planner = make_simplified_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3))], name="go home")
    assert plan.explanation == "go home"


def test_plan_default_explanation_when_no_name(pip):
    planner = make_simplified_planner()
    plan = planner.plan([MoveSpec(pip, np.zeros(3))])
    assert plan.explanation == "motion plan"


# ---------------------------------------------------------------------------
# InteractionSite approach — parallel group structure with movable stage
# ---------------------------------------------------------------------------

def test_movable_site_approach_contains_parallel_group(pip):
    """The plan must contain a ParallelGroup when the site has a movable stage."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.save_approach_for(pip, calibrated_approach)
    stage_target = np.array([2e-3, 0.0, 0.0])
    site.approachMoveSpec = lambda p, speed="fast": _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])

    parallel_groups = _collect_parallel_groups(plan)
    assert len(parallel_groups) >= 1


def test_movable_site_approach_parallel_group_contains_pip_and_stage():
    """When pip starts below approach depth, the parallel group lifts it alongside the stage move."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    # pip below approach depth — lift is needed
    pip = MockPipette("pip1", global_pos=(0.0, 0.0, -2e-3), approach_depth=0.0)
    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.save_approach_for(pip, calibrated_approach)
    stage_target = np.array([2e-3, 0.0, 0.0])
    site.approachMoveSpec = lambda p, speed="fast": _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])

    parallel_groups = _collect_parallel_groups(plan)
    # At least one ParallelGroup must contain both a pip move and a stage move
    found = False
    for pg in parallel_groups:
        members = _flatten(pg)
        has_pip = any(m.device is pip for m in members)
        has_stage = any(m.device is stage for m in members)
        if has_pip and has_stage:
            found = True
            break
    assert found, "No ParallelGroup contained both pip and stage moves"


def test_movable_site_no_pip_lift_when_already_at_safe_z():
    """When pip is already at or above approach depth, no pip lift is added to the plan."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    # pip at exactly approach depth — already safe, no lift needed
    pip = MockPipette("pip1", global_pos=(0.0, 0.0, 0.0), approach_depth=0.0)
    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.save_approach_for(pip, calibrated_approach)
    stage_target = np.array([2e-3, 0.0, 0.0])
    site.approachMoveSpec = lambda p, speed="fast": _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])

    parallel_groups = _collect_parallel_groups(plan)
    for pg in parallel_groups:
        members = _flatten(pg)
        pip_moves = [m for m in members if m.device is pip]
        assert len(pip_moves) == 0, "Pip should not be lifted when already at safe z"


def test_movable_site_approach_pip_lift_is_parallel_not_sequential():
    """When pip needs lifting, it must rise in the same ParallelGroup as the stage, not before it."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    # pip below approach depth — lift will be added to the parallel group
    pip = MockPipette("pip1", global_pos=(0.0, 0.0, -2e-3), approach_depth=0.0)
    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.save_approach_for(pip, calibrated_approach)
    stage_target = np.array([2e-3, 0.0, 0.0])
    site.approachMoveSpec = lambda p, speed="fast": _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])

    # plan → SequentialGroup("motion plan") → SequentialGroup("interact with …") → ParallelGroup(…)
    assert isinstance(plan, SequentialGroup)
    approach_group = plan.steps[0]
    assert isinstance(approach_group, SequentialGroup)
    first_child = approach_group.steps[0]
    assert isinstance(first_child, ParallelGroup), (
        "First step of the approach SequentialGroup must be a ParallelGroup (stage reposition, + pip lift when needed)"
    )
    members = _flatten(first_child)
    assert any(m.device is pip for m in members), "Pip lift must be inside the ParallelGroup"
    assert any(m.device is stage for m in members), "Stage reposition must be inside the ParallelGroup"


# ---------------------------------------------------------------------------
# _safe_path behaviour — speed enforcement, named waypoints, retraction
# ---------------------------------------------------------------------------
#
# Geometry for the inward tests (pip at (0,0,5e-3), pitch=π/4, approachDepth=0):
#   Move from pip.globalPosition() → (5e-3, 0, -3e-3)
#   Approach waypoint = positionAtDepth(0, start=(5e-3,0,-3e-3)) = (2e-3, 0, 0).
#   Path: APPROACH_WAYPOINT (2e-3,0,0) @ fast, MOVE_TO_DESTINATION (5e-3,0,-3e-3) @ slow.
#
# Geometry for the above-surface test (pip at (0,0,5e-3), approachDepth=0):
#   Move from pip.globalPosition() → (5e-3, 0, 3e-3)  — stays above z=0 throughout.
#
# Geometry for the retraction test (pip at (0,0,-2e-3), approachDepth=0):
#   Lateral (y-direction) move while both endpoints are below approachDepth → retraction.
#   retract_pos = positionAtDepth(0, start=(0,0,-2e-3)) = (-2e-3, 0, 0) at pitch=π/4.


@pytest.fixture
def real_pip_above():
    """Pipette above approachDepth=0, positioned so inward moves cross the boundary."""
    return MockPipette("pip_above", global_pos=(0.0, 0.0, 5e-3), approach_depth=0.0)


@pytest.fixture
def real_pip_below():
    """Pipette below approachDepth=0, so lateral moves require retraction first."""
    return MockPipette("pip_below", global_pos=(0.0, 0.0, -2e-3), approach_depth=0.0)


def test_inward_move_approach_waypoint_on_pipette_axis(real_pip_above):
    """Entering tissue: approach waypoint must be positionAtDepth(approachDepth, start=target)."""
    pip = real_pip_above
    target = np.array([5e-3, 0.0, -3e-3])
    expected_wp = pip.positionAtDepth(pip.approachDepth(), start=target)

    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), target, "fast")

    positions = [step[0] for step in path]
    assert any(np.allclose(p, expected_wp, atol=1e-9) for p in positions), (
        f"Expected approach waypoint {expected_wp} in path, got {positions}"
    )
    wp_idx = next(i for i, p in enumerate(positions) if np.allclose(p, expected_wp, atol=1e-9))
    tgt_idx = next(i for i, p in enumerate(positions) if np.allclose(p, target, atol=1e-9))
    assert wp_idx < tgt_idx, "Approach waypoint must precede tissue destination"


def test_outward_move_exit_waypoint_on_pipette_axis(real_pip_below):
    """Exiting tissue: exit waypoint must be positionAtDepth(approachDepth, start=globalStart)."""
    pip = real_pip_below
    target = np.array([0.0, 0.0, 5e-3])
    expected_wp = pip.positionAtDepth(pip.approachDepth(), start=pip.globalPosition())

    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), target, "fast")

    positions = [step[0] for step in path]
    assert any(np.allclose(p, expected_wp, atol=1e-9) for p in positions), (
        f"Expected exit waypoint {expected_wp} in path, got {positions}"
    )
    wp_idx = next(i for i, p in enumerate(positions) if np.allclose(p, expected_wp, atol=1e-9))
    tgt_idx = next(i for i, p in enumerate(positions) if np.allclose(p, target, atol=1e-9))
    assert wp_idx < tgt_idx, "Exit waypoint must precede above-tissue destination"


def test_safe_path_approach_waypoint_is_named(real_pip_above):
    """_safe_path must label the lateral-avoidance waypoint APPROACH_WAYPOINT."""
    from acq4.motion.default_planner import APPROACH_WAYPOINT

    pip = real_pip_above
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, -3e-3]), "fast")
    names = [step[3] for step in path]
    assert APPROACH_WAYPOINT in names, f"Expected APPROACH_WAYPOINT in {names}"


def test_safe_path_final_step_is_named_move_to_destination(real_pip_above):
    """The last path step must be labelled MOVE_TO_DESTINATION."""
    from acq4.motion.default_planner import MOVE_TO_DESTINATION

    pip = real_pip_above
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, -3e-3]), "fast")
    assert path[-1][3] == MOVE_TO_DESTINATION



def test_safe_path_slow_speed_below_approach_depth(real_pip_above):
    """Segments that end below approachDepth must run at 'slow', not 'fast'."""
    pip = real_pip_above
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, -3e-3]), "fast")
    # Every step whose destination is below approachDepth must be slow
    slow_depth = pip.approachDepth()
    for pos, speed, _linear, _name in path:
        if pos[2] < slow_depth:
            assert speed == "slow", f"Step to {pos} at z={pos[2]} below approachDepth should be slow, got {speed!r}"


def test_safe_path_fast_speed_above_approach_depth(real_pip_above):
    """Moves that stay entirely above approachDepth must not be forced to slow."""
    pip = real_pip_above
    planner = make_real_planner()
    # Move stays at z=3e-3, well above approachDepth=0
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, 3e-3]), "fast")
    slow_depth = pip.approachDepth()
    for pos, speed, _linear, name in path:
        assert speed != "slow", f"Step '{name}' to {pos} above approachDepth was unexpectedly slowed"


def test_safe_path_enforces_slow_when_caller_requests_slow(real_pip_above):
    """When the caller passes speed='slow', all steps must be slow."""
    pip = real_pip_above
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, 3e-3]), "slow")
    for pos, speed, _linear, name in path:
        assert speed == "slow", f"Step '{name}' was not slow despite speed='slow' request"


def test_safe_path_retracts_before_lateral_inside_sample(real_pip_below):
    """Lateral movement while both endpoints are below approachDepth must begin with a retraction."""
    from acq4.motion.default_planner import RETRACTION_TO_AVOID_SAMPLE_TEAR

    pip = real_pip_below
    planner = make_real_planner()
    # Pure y-direction move — both z values below approachDepth=0
    path = planner._safe_path(pip, pip.globalPosition(), np.array([0.0, 3e-3, -2e-3]), "fast")
    assert path[0][3] == RETRACTION_TO_AVOID_SAMPLE_TEAR, (
        f"First step should retract; got {path[0][3]!r}"
    )


def test_safe_path_retraction_uses_slow_speed(real_pip_below):
    """The retraction step must be slow to avoid tearing the sample."""
    from acq4.motion.default_planner import RETRACTION_TO_AVOID_SAMPLE_TEAR

    pip = real_pip_below
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([0.0, 3e-3, -2e-3]), "fast")
    retract_step = next(s for s in path if s[3] == RETRACTION_TO_AVOID_SAMPLE_TEAR)
    assert retract_step[1] == "slow", "Retraction step must use slow speed"


def test_safe_path_retraction_reaches_approach_depth(real_pip_below):
    """The retraction waypoint must be at or above approachDepth."""
    from acq4.motion.default_planner import RETRACTION_TO_AVOID_SAMPLE_TEAR

    pip = real_pip_below
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([0.0, 3e-3, -2e-3]), "fast")
    retract_step = next(s for s in path if s[3] == RETRACTION_TO_AVOID_SAMPLE_TEAR)
    assert retract_step[0][2] >= pip.approachDepth(), (
        f"Retraction target z={retract_step[0][2]} is still below approachDepth={pip.approachDepth()}"
    )


def test_safe_path_no_retraction_when_above_approach_depth(real_pip_above):
    """No retraction should occur when the pipette starts above approachDepth."""
    from acq4.motion.default_planner import RETRACTION_TO_AVOID_SAMPLE_TEAR

    pip = real_pip_above
    planner = make_real_planner()
    # Lateral move entirely above surface
    path = planner._safe_path(pip, pip.globalPosition(), np.array([0.0, 3e-3, 5e-3]), "fast")
    names = [s[3] for s in path]
    assert RETRACTION_TO_AVOID_SAMPLE_TEAR not in names, (
        "Unexpected retraction for a move entirely above approachDepth"
    )


def test_safe_path_limit_exceeded_raises_value_error(real_pip_above):
    """When checkGlobalLimits raises, _safe_path must re-raise as ValueError."""
    pip = real_pip_above
    pip._parent_stage.checkGlobalLimits = lambda pos, linear=False: (_ for _ in ()).throw(
        RuntimeError("out of range")
    )
    planner = make_real_planner()
    with pytest.raises(ValueError, match="beyond the limits"):
        planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, -3e-3]), "fast")


# ---------------------------------------------------------------------------
# Spec validation (_validate_specs) — duplicate devices and relative-to ordering
# ---------------------------------------------------------------------------

def test_duplicate_device_in_specs_raises(pip):
    """Two specs for the same device must raise PlanningError."""
    planner = make_simplified_planner()
    specs = [
        MoveSpec(pip, np.array([1e-3, 0.0, 0.0])),
        MoveSpec(pip, np.array([2e-3, 0.0, 0.0])),
    ]
    with pytest.raises(PlanningError, match="can only have one final position"):
        planner._validate_specs(specs)


def test_relative_to_anchor_moved_later_raises():
    """Spec A relative to device X, with X moved by a later spec B, must raise PlanningError."""
    planner = make_simplified_planner()
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    dev = MockDevice("dev1")
    specs = [
        MoveSpec(dev, np.array([1e-3, 0.0, 0.0]), relative_to=anchor),
        MoveSpec(anchor, np.array([20e-3, 0.0, 0.0])),
    ]
    with pytest.raises(PlanningError, match="anchor device is moved by spec"):
        planner._validate_specs(specs)


def test_relative_to_anchor_moved_first_passes():
    """When the anchor device is moved before the relative spec, validation must pass."""
    planner = make_simplified_planner()
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    dev = MockDevice("dev1")
    planner._validate_specs([
        MoveSpec(anchor, np.array([20e-3, 0.0, 0.0])),
        MoveSpec(dev, np.array([1e-3, 0.0, 0.0]), relative_to=anchor),
    ])  # must not raise


def test_relative_to_interaction_site_not_flagged_as_ordering_error(pip, site):
    """Relative-to ordering check must not fire for InteractionSite anchors."""
    planner = make_simplified_planner()
    planner._validate_specs([MoveSpec(pip, np.zeros(3), relative_to=site)])  # must not raise


def test_wrong_relative_to_order_produces_wrong_position_without_validation():
    """Demonstrate the silent failure that spec validation prevents.

    Without the check: dev ends at local_pos resolved against anchor's CURRENT (old) position,
    not against the new position the anchor is moved to later in the same plan.
    """
    from acq4.motion.default_planner import DefaultMotionPlanner

    class _SimplePath(DefaultMotionPlanner):
        def _safe_path(self, pip, gs, gt, speed, explanation=None):
            return [(np.asarray(gt, dtype=float), speed, False, explanation or "move")]

    planner = _SimplePath()
    anchor = MockDevice("anchor", (10e-3, 0.0, 0.0))
    dev = MockDevice("dev1")
    specs = [
        MoveSpec(dev, np.array([1e-3, 0.0, 0.0]), relative_to=anchor),   # OLD anchor pos
        MoveSpec(anchor, np.array([20e-3, 0.0, 0.0])),                    # anchor moves AFTER
    ]

    # Bypassing _validate_specs to show the wrong-position result
    plan = SequentialGroup([planner._plan_one(s) for s in specs], "bad plan")
    moves = _flatten(plan)
    dev_move = next(m for m in moves if m.device is dev)
    # resolves to (11e-3,0,0) — the correct answer if anchor moved first would be (21e-3,0,0)
    np.testing.assert_array_almost_equal(dev_move.position, [11e-3, 0.0, 0.0])

    # Now confirm _validate_specs catches it
    with pytest.raises(PlanningError, match="anchor device is moved by spec"):
        planner._validate_specs(specs)


# ---------------------------------------------------------------------------
# Post-plan sanity checks (_validate_plan)
# ---------------------------------------------------------------------------

def test_plan_final_position_matches_spec_for_generic_device():
    """_validate_plan must not raise when the plan correctly ends at the spec target."""
    planner = make_simplified_planner()
    dev = MockDevice("dev1")
    target = np.array([3e-3, 0.0, 0.0])
    specs = [MoveSpec(dev, target)]
    plan = planner.plan(specs)
    planner._validate_plan(specs, plan)  # must not raise
    moves = _flatten(plan)
    np.testing.assert_array_almost_equal(moves[-1].position, target)


def test_plan_final_position_matches_spec_for_pipette(pip):
    """_validate_plan must pass for a simple pipette move ending at the target."""
    planner = make_simplified_planner()
    target = np.array([0.0, 0.0, 5e-3])
    specs = [MoveSpec(pip, target)]
    plan = planner.plan(specs)
    planner._validate_plan(specs, plan)  # must not raise


def test_validate_plan_catches_wrong_final_position():
    """_validate_plan raises PlanningError when the plan ends at the wrong position."""
    from acq4.motion.default_planner import DefaultMotionPlanner

    planner = make_simplified_planner()
    dev = MockDevice("dev1")
    specs = [MoveSpec(dev, np.array([1e-3, 0.0, 0.0]))]
    # Craft a plan that deliberately puts dev at the wrong position
    wrong_plan = SequentialGroup([AtomicMove(dev, np.array([99.0, 0.0, 0.0]), "fast", "wrong")])
    with pytest.raises(PlanningError, match="Plan inconsistency"):
        planner._validate_plan(specs, wrong_plan)
