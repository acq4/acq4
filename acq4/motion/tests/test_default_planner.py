# Tests for DefaultMotionPlanner.plan().
# The default planner is rig-agnostic: no scope parking, no unwind logic.
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.planner import PlanningError
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import MockDevice, MockInteractionSite, MockPipette, MockScope, MockStage


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


def test_direct_access_site_skips_approach_waypoint(pip, site_with_direct_access):
    """Sites with directAccess: true skip the approach waypoint enforcement."""
    planner = make_simplified_planner()
    interact_local = np.array(site_with_direct_access.positions[pip.name()]["interact local"])
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site_with_direct_access)])
    moves = _flatten(plan)
    pip_moves = [m for m in moves if m.device is pip]
    approach_global = np.array(site_with_direct_access.globalPosition())
    interact_global = np.array(site_with_direct_access.positions[pip.name()]["interact global"])
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
    site.positions[pip.name()]["site global"] = list(calibrated_approach)

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
# InteractionSite exit — approach waypoint prepended when pip is inside a site
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
    site.positions[pip.name()]["site global"] = list(calibrated_approach)
    stage_target = np.array([2e-3, 0.0, 0.0])
    site.approachMoveSpec = lambda p, speed="fast": _MoveSpec(stage, stage_target, speed=speed)
    site.approachGlobal = lambda p: calibrated_approach

    planner = make_simplified_planner()
    interact_local = np.array(site.positions[pip.name()]["interact local"])
    plan = planner.plan([_MoveSpec(pip, interact_local, relative_to=site)])

    parallel_groups = _collect_parallel_groups(plan)
    assert len(parallel_groups) >= 1


def test_movable_site_approach_parallel_group_contains_pip_and_stage(pip):
    """The parallel group must move both the pip (lift) and the stage (reposition) together."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.positions[pip.name()]["site global"] = list(calibrated_approach)
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


def test_movable_site_approach_pip_lift_is_parallel_not_sequential(pip):
    """The pip must rise at the same time as the stage repositions, not before or after."""
    from acq4.motion.spec import MoveSpec as _MoveSpec

    stage = MockStage("well_stage", (3e-3, 0.0, 0.0))
    site = MockInteractionSite("cleanwell", global_pos=(6e-3, 0.0, -2e-3))
    calibrated_approach = np.array([5e-3, 0.0, -2e-3])
    interact_global = np.array([5e-3, 0.0, -3e-3])
    site.save_positions_for(pip, interact_global)
    site.positions[pip.name()]["site global"] = list(calibrated_approach)
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
        "First step of the approach SequentialGroup must be a ParallelGroup (pip lift + stage reposition)"
    )


# ---------------------------------------------------------------------------
# _safe_path behaviour — speed enforcement, named waypoints, retraction
# ---------------------------------------------------------------------------
#
# Geometry for the inward tests (pip at (0,0,5e-3), pitch=π/4, approachDepth=0):
#   Move from pip.globalPosition() → (5e-3, 0, -3e-3)
#   Computes APPROACH_WAYPOINT at (0,0,2e-3), then splits at approachDepth=0:
#     SAFE_SPEED_WAYPOINT (0,0,0) @ fast, MOVE_TO_DESTINATION (5e-3,0,-3e-3) @ slow.
#
# Geometry for the above-surface test (pip at (0,0,5e-3), approachDepth=0):
#   Move from pip.globalPosition() → (5e-3, 0, 3e-3)  — stays above z=0 throughout.
#
# Geometry for the retraction test (pip at (0,0,-2e-3), approachDepth=0):
#   Lateral (y-direction) move while both endpoints are below approachDepth → retraction.


@pytest.fixture
def real_pip_above():
    """Pipette above approachDepth=0, positioned so inward moves cross the boundary."""
    return MockPipette("pip_above", global_pos=(0.0, 0.0, 5e-3), approach_depth=0.0)


@pytest.fixture
def real_pip_below():
    """Pipette below approachDepth=0, so lateral moves require retraction first."""
    return MockPipette("pip_below", global_pos=(0.0, 0.0, -2e-3), approach_depth=0.0)


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


def test_safe_path_safe_speed_waypoint_named_when_crossing_approach_depth(real_pip_above):
    """When the path crosses approachDepth the speed-transition waypoint must be named SAFE_SPEED_WAYPOINT."""
    from acq4.motion.default_planner import SAFE_SPEED_WAYPOINT

    pip = real_pip_above
    planner = make_real_planner()
    path = planner._safe_path(pip, pip.globalPosition(), np.array([5e-3, 0.0, -3e-3]), "fast")
    names = [step[3] for step in path]
    assert SAFE_SPEED_WAYPOINT in names, f"Expected SAFE_SPEED_WAYPOINT in {names}"


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
