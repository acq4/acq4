# Tests for MinirigV1MotionPlanner — scope-park / scope-unwind behaviour.
from __future__ import annotations

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup
from acq4.motion.spec import MoveSpec
from acq4.motion.tests.conftest import (
    MockInteractionSite,
    MockMobileInteractionSite,
    MockPipette,
    MockScope,
    MockStage,
)


def make_planner():
    from acq4.motion.minirig_v1 import MinirigV1MotionPlanner

    class _TestPlanner(MinirigV1MotionPlanner):
        def _safe_path(self, pip, globalStart, globalStop, speed, explanation=None):
            return [
                (
                    np.asarray(globalStop, dtype=float),
                    speed,
                    False,
                    explanation or "move",
                )
            ]

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


def test_scope_park_not_repeated_when_the_scope_is_already_there(pip, site_with_scope_park):
    """An approach skips the park moves only when the scope really is at park."""
    planner = make_planner()
    scope = pip.scopeDevice()
    park = np.asarray(site_with_scope_park.config["scopeParkPos"], dtype=float)
    scope._global_pos = park.copy()

    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flat_moves(plan) if isinstance(m.device, MockScope)]
    assert len(scope_moves) == 0


def test_the_pipette_clears_the_wells_even_when_the_scope_is_already_parked(pip):
    """The rack must never move while the pipette is still down in a tube."""
    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, global_pos=(5e-3, 0.0, -2e-3), approach=(40e-3, 0.0, -2e-3))
    planner = _planner_knowing([site])
    pip.scopeDevice()._global_pos = PARK.copy()

    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site)])
    moves = _flat_moves(plan)

    assert not any(isinstance(m.device, MockScope) for m in moves), "already parked"
    home_idx = [
        i for i, m in enumerate(moves)
        if m.device is pip and np.allclose(m.position, pip.homePosition())
    ]
    stage_idx = [i for i, m in enumerate(moves) if m.device is stage]
    assert home_idx and stage_idx
    assert max(home_idx) < min(stage_idx), "pipette must reach home before the stage moves"


def test_a_stale_context_does_not_stop_the_scope_being_parked(pip, site_with_scope_park):
    """A context left behind by a failed plan must not be read as 'the scope is parked'.

    The context is written during plan(), before any motor turns, so a failure anywhere in
    execution leaves one behind.  Trusting it skipped the park entirely and moved the stage
    with the objective wherever the failure left it.
    """
    planner = make_planner()
    scope = pip.scopeDevice()
    site = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3))
    planner._scope_context[pip.name()] = (
        scope,
        [np.zeros(3), np.zeros(3), np.zeros(3)],
        pip,
        site,
    )

    plan = planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])
    scope_moves = [m for m in _flat_moves(plan) if isinstance(m.device, MockScope)]
    assert scope_moves, "the scope must be parked; the leftover context proves nothing"


def test_a_stale_context_keeps_its_original_position(pip, site_with_scope_park):
    """Re-parking must not record the half-parked position as the scope's home."""
    planner = make_planner()
    scope = pip.scopeDevice()
    home = np.array([1e-3, 2e-3, 3e-3])
    site = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3))
    planner._scope_context[pip.name()] = (scope, [home, np.zeros(3), np.zeros(3)], pip, site)

    planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site_with_scope_park)])

    np.testing.assert_array_almost_equal(
        planner._scope_context[pip.name()][1][0], home
    )


# ---------------------------------------------------------------------------
# Scope unwind on return home (via _plan_pipette_move fallback)
# ---------------------------------------------------------------------------


def _seed_scope_context(planner, pip):
    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    site = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3))
    planner._scope_context[pip.name()] = (
        scope,
        [original_pos, up_pos, park_pos],
        pip,
        site,
    )
    # A context describes a scope that has been parked, so put it where it says it is.
    scope._global_pos = park_pos.copy()
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
    """Unwind walks the forward park path backwards, re-commanding park before descending."""
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)

    planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    # re-seed and re-plan to inspect the generated scope moves
    site = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3))
    planner._scope_context[pip.name()] = (
        scope,
        [original_pos, up_pos, park_pos],
        pip,
        site,
    )
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    moves = _flat_moves(plan)
    scope_moves = [m for m in moves if m.device is scope]

    expected = list(reversed([original_pos, up_pos, park_pos]))
    assert len(scope_moves) == len(expected)
    for move, waypoint in zip(scope_moves, expected):
        np.testing.assert_array_almost_equal(move.position, waypoint)


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
        [
            pip.scopeDevice().globalPosition()[0],
            pip.scopeDevice().globalPosition()[1],
            park_pos[2],
        ]
    )
    np.testing.assert_array_almost_equal(
        moves[0].position,
        up_pos,
        err_msg="First scope move must be z-only (up to park height)",
    )


def test_pip_retract_before_scope_lateral_when_pip_in_tissue(site_with_scope_park):
    """When pip starts below approach depth, it must retract before scope moves laterally."""
    pip_below = MockPipette(
        "pip_below", global_pos=(0.0, 0.0, -3e-3), approach_depth=0.0
    )
    site_with_scope_park.save_positions_for(pip_below, np.array([0.0, 0.0, -1e-3]))
    site_with_scope_park.save_approach_for(pip_below)

    planner = make_planner()
    plan = planner.plan(
        [MoveSpec(pip_below, np.zeros(3), relative_to=site_with_scope_park)]
    )
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
    plan = planner.plan(
        [MoveSpec(pip_safe, np.zeros(3), relative_to=site_with_scope_park)]
    )
    moves = _flat_moves(plan)

    # scope up, pip home, scope lateral, then pip.  The unconditional go-home step is the
    # only pip move allowed between scope-up and scope-lateral; the retract-to-approach-depth
    # step must be absent because the pip already sits at its approach depth.
    scope_idxs = [i for i, m in enumerate(moves) if isinstance(m.device, MockScope)]
    pip_idxs = [i for i, m in enumerate(moves) if m.device is pip_safe]
    assert len(scope_idxs) >= 2
    between = [moves[i] for i in pip_idxs if scope_idxs[0] < i < scope_idxs[1]]
    assert [m.explanation for m in between] == [
        "pipette home before scope park"
    ], "No pip retract step should appear between scope-up and scope-lateral"


# ---------------------------------------------------------------------------
# Scope unwind via interaction exit (_plan_interaction_exit path)
# ---------------------------------------------------------------------------


def test_scope_unwind_appended_after_interaction_exit(pip, site_with_scope_park):
    """When pip exits a site via _plan_interaction_exit, scope unwind is still appended."""
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)
    approach_global = np.array(site_with_scope_park.globalPosition())
    planner._find_containing_site = lambda dev: (
        site_with_scope_park if dev is pip else None
    )

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


# ---------------------------------------------------------------------------
# Scope unwind + pipette extraction on stage (or stage-child) moves
# ---------------------------------------------------------------------------


def _seed_mobile_site_context(planner, pip, *, inside=True):
    """Seed scope context for *pip* docked in a mobile site mounted on a parent stage.

    Returns (scope, stage, site, original_pos, up_pos, park_pos).  When ``inside`` is True the
    planner's containment check reports the pipette as being inside the site.
    """
    scope = pip.scopeDevice()
    original_pos = np.array([0.0, 0.0, 10e-3])
    up_pos = np.array([0.0, 0.0, 15e-3])
    park_pos = np.array([20e-3, 0.0, 15e-3])
    stage = MockStage("well_stage", global_pos=(0.0, 0.0, 0.0))
    site = MockInteractionSite(
        "cleanwell", global_pos=(5e-3, 0.0, -2e-3), parent_stage=stage
    )
    site.save_positions_for(pip, np.array([0.0, 0.0, -1e-3]))
    site.save_approach_for(pip)
    planner._scope_context[pip.name()] = (
        scope,
        [original_pos, up_pos, park_pos],
        pip,
        site,
    )
    planner._find_containing_site = lambda dev: (
        site if (inside and dev is pip) else None
    )
    scope._global_pos = park_pos.copy()
    return scope, stage, site, original_pos, up_pos, park_pos


def test_stage_move_order_is_extract_then_unwind_then_move(pip):
    """A parent-stage move first extracts the pip, then unwinds the scope, then moves the stage."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=True)

    plan = planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    moves = _flat_moves(plan)

    pip_idxs = [i for i, m in enumerate(moves) if m.device is pip]
    scope_idxs = [i for i, m in enumerate(moves) if m.device is scope]
    stage_idxs = [i for i, m in enumerate(moves) if m.device is stage]

    assert pip_idxs and scope_idxs and stage_idxs
    assert max(pip_idxs) < min(scope_idxs), "pip extraction must precede scope unwind"
    assert max(scope_idxs) < min(stage_idxs), "scope unwind must precede the stage move"
    assert stage_idxs == [len(moves) - 1], "the stage move must be the final step"


def test_stage_move_extracts_via_approach_then_home(pip):
    """Extraction exits via the site's approach waypoint and finishes at the pipette home."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=True)
    approach = np.array(site.approachGlobal(pip))
    home = np.array(pip.homePosition())

    plan = planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    pip_moves = [m for m in _flat_moves(plan) if m.device is pip]

    assert len(pip_moves) >= 2
    np.testing.assert_array_almost_equal(pip_moves[0].position, approach)
    np.testing.assert_array_almost_equal(pip_moves[-1].position, home)


def test_stage_move_unwinds_but_does_not_extract_when_pip_not_inside(pip):
    """When the pip is not inside the site, the scope still unwinds but no extraction is added."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=False)

    plan = planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    moves = _flat_moves(plan)

    assert not any(
        m.device is pip for m in moves
    ), "no extraction when pip is not inside the site"
    assert any(m.device is scope for m in moves), "scope still unwinds"
    assert any(m.device is stage for m in moves)


def test_stage_child_move_triggers_unwind(pip):
    """Moving a child of the stage (the site itself) also triggers extraction + unwind."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=True)

    plan = planner.plan([MoveSpec(site, np.array([6e-3, 0.0, -2e-3]))])
    moves = _flat_moves(plan)

    assert any(
        m.device is scope for m in moves
    ), "scope unwind triggered by stage-child move"
    assert any(m.device is pip for m in moves), "pip extracted on stage-child move"
    assert moves[-1].device is site, "the site's own move runs last"


def test_unrelated_generic_move_leaves_scope_parked(pip):
    """A move of a device outside the docked site's stage subtree does not unwind anything."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=True)
    other = MockStage("other_stage", global_pos=(0.0, 0.0, 0.0))

    plan = planner.plan([MoveSpec(other, np.array([1e-3, 0.0, 0.0]))])
    moves = _flat_moves(plan)

    assert not any(m.device is scope for m in moves)
    assert not any(m.device is pip for m in moves)
    assert len(moves) == 1 and moves[0].device is other
    assert (
        pip.name() in planner._scope_context
    ), "context preserved for an unrelated move"


def test_stage_move_clears_context(pip):
    """The scope context is popped once the stage move has consumed it."""
    planner = make_planner()
    scope, stage, site, *_ = _seed_mobile_site_context(planner, pip, inside=True)

    planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    assert pip.name() not in planner._scope_context


def test_generic_move_without_context_is_a_plain_move(stage):
    """With no scope parked, a generic device move is a single untouched atomic move."""
    planner = make_planner()
    plan = planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    moves = _flat_moves(plan)
    assert len(moves) == 1 and moves[0].device is stage


# ---------------------------------------------------------------------------
# Lock-failure recovery: _on_lock_failure restores scope context
# ---------------------------------------------------------------------------
# These tests exercise the fix for the bug where _scope_context.pop() happens
# inside plan() (before reserveDevices()), so a failed lock acquisition leaves
# the scope permanently parked with no context record.  The tests call plan()
# and _on_lock_failure() directly, bypassing execute() / Qt / hardware.


def test_on_lock_failure_restores_popped_context(pip):
    """After a lock failure, _scope_context is restored to its pre-plan state."""
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    assert pip.name() not in planner._scope_context, "plan() should pop the context"

    planner._on_lock_failure(plan)

    assert pip.name() in planner._scope_context, "context must be restored after lock failure"
    restored = planner._scope_context[pip.name()]
    np.testing.assert_array_almost_equal(restored[1][0], original_pos)
    np.testing.assert_array_almost_equal(restored[1][1], up_pos)
    np.testing.assert_array_almost_equal(restored[1][2], park_pos)


def test_on_lock_failure_does_not_overwrite_updated_context(pip):
    """If another thread already wrote a new context for the pip, don't clobber it."""
    planner = make_planner()
    _seed_scope_context(planner, pip)

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])

    # Simulate another call having already restored / re-seeded the context
    new_ctx = (pip.scopeDevice(), [np.ones(3), np.ones(3), np.ones(3)], pip, None)
    planner._scope_context[pip.name()] = new_ctx

    planner._on_lock_failure(plan)

    # The new context must not be overwritten (setdefault semantics)
    assert planner._scope_context[pip.name()] is new_ctx


def test_on_lock_failure_only_restores_consumed_entries(pip):
    """Contexts for pipettes not involved in the plan are left untouched."""
    pip2 = MockPipette("pip2", global_pos=(0.0, 0.0, 0.0))
    planner = make_planner()
    _seed_scope_context(planner, pip)

    pip2_ctx = (pip.scopeDevice(), [np.zeros(3), np.zeros(3), np.zeros(3)], pip2, None)
    planner._scope_context["pip2"] = pip2_ctx

    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    # pip's context was popped; pip2's was not
    assert pip.name() not in planner._scope_context
    assert planner._scope_context["pip2"] is pip2_ctx

    planner._on_lock_failure(plan)

    assert pip.name() in planner._scope_context
    assert planner._scope_context["pip2"] is pip2_ctx  # untouched


def test_on_lock_failure_without_prior_plan_is_safe(pip):
    """Calling _on_lock_failure before any plan() call must not raise."""
    planner = make_planner()
    planner._on_lock_failure(None)  # no snapshot yet — should be a no-op


def test_repeated_lock_failure_does_not_accumulate_context(pip):
    """Two consecutive plan()+_on_lock_failure() cycles restore once, not twice."""
    planner = make_planner()
    scope, original_pos, up_pos, park_pos = _seed_scope_context(planner, pip)

    for _ in range(2):
        plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
        planner._on_lock_failure(plan)

    # Context should be present exactly once with the original values
    assert pip.name() in planner._scope_context
    restored = planner._scope_context[pip.name()]
    np.testing.assert_array_almost_equal(restored[1][0], original_pos)


# ---------------------------------------------------------------------------
# Certifying a direct stage move to the park position
# ---------------------------------------------------------------------------
# Without collision detection the planner cannot prove an arbitrary path is clear, so it
# only drives to park from a pose it has grounds to trust: already at or above park
# height, or sitting at a saved well approach pose.  Anything else is refused -- the dial
# jogs bypass the planner, so an operator is never stranded by a refusal.

PARK = np.array([20e-3, 0.0, 15e-3])


def _mobile_site(stage, name="well", global_pos=(5e-3, 0.0, -2e-3), approach=None):
    """A site on *stage* with a saved approach position, like an array child."""
    site = MockMobileInteractionSite(
        name, global_pos=global_pos, scope_park_pos=PARK, parent_stage=stage
    )
    site.positions["pip1"] = {
        "site global": list(np.asarray(approach if approach is not None else global_pos, dtype=float)),
        "interact global": [0.0, 0.0, -1e-3],
        "interact local": list(np.asarray([0.0, 0.0, -1e-3]) - np.asarray(global_pos)),
    }
    return site


def _planner_knowing(sites):
    planner = make_planner()
    planner._interaction_sites = lambda: list(sites)
    return planner


def _unwind_targets(planner, pip):
    plan = planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])
    return [m for m in _flat_moves(plan) if m.device is pip.scopeDevice()]


def test_unwind_retraces_the_recorded_path_when_the_scope_is_at_park(pip):
    planner = _planner_knowing([])
    scope = pip.scopeDevice()
    original_pos, up_pos = np.array([0.0, 0.0, 10e-3]), np.array([0.0, 0.0, 15e-3])
    planner._scope_context[pip.name()] = (
        scope, [original_pos, up_pos, PARK], pip, MockInteractionSite("w")
    )
    scope._global_pos = PARK.copy()

    targets = [m.position for m in _unwind_targets(planner, pip)]

    assert len(targets) == 3
    np.testing.assert_array_almost_equal(targets[-1], original_pos)


def test_unwind_refuses_from_a_low_pose_that_is_not_a_well(pip):
    """The old code cut a diagonal to park from wherever the scope happened to be."""
    from acq4.motion.planner import PlanningError

    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, approach=(5e-3, 0.0, 50e-3))
    planner = _planner_knowing([site])
    scope = pip.scopeDevice()
    planner._scope_context[pip.name()] = (scope, [np.zeros(3), np.zeros(3), PARK], pip, site)
    scope._global_pos = np.array([0.0, 0.0, -5e-3])  # well below park height
    stage._global_pos = np.array([99e-3, 99e-3, 99e-3])  # nowhere near a well

    with pytest.raises(PlanningError, match="park"):
        planner.plan([MoveSpec(pip, np.array([0.0, 0.0, 5e-3]))])


def test_unwind_is_allowed_from_at_or_above_park_height(pip):
    planner = _planner_knowing([])
    scope = pip.scopeDevice()
    planner._scope_context[pip.name()] = (
        scope, [np.zeros(3), np.zeros(3), PARK], pip, MockInteractionSite("w")
    )
    scope._global_pos = np.array([0.0, 0.0, PARK[2] + 5e-3])

    assert _unwind_targets(planner, pip), "above park height is certified"


def test_unwind_is_allowed_from_a_saved_well_approach_pose(pip):
    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, approach=(5e-3, 0.0, -2e-3))  # approach == current pose
    planner = _planner_knowing([site])
    scope = pip.scopeDevice()
    planner._scope_context[pip.name()] = (scope, [np.zeros(3), np.zeros(3), PARK], pip, site)
    scope._global_pos = np.array([0.0, 0.0, -5e-3])  # low, but parked at a well

    assert _unwind_targets(planner, pip), "a saved well approach pose is certified"


# ---------------------------------------------------------------------------
# Hub rule: from a well approach pose, park is the only permitted stage target
# ---------------------------------------------------------------------------


def test_a_stage_move_from_a_well_pose_must_target_park(pip):
    from acq4.motion.planner import PlanningError

    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, approach=(5e-3, 0.0, -2e-3))
    planner = _planner_knowing([site])
    planner._scope_for_stage = lambda s: pip.scopeDevice()

    with pytest.raises(PlanningError, match="park"):
        planner.plan([MoveSpec(stage, np.array([50e-3, 50e-3, 50e-3]))])


def test_a_stage_move_from_a_well_pose_to_park_is_allowed(pip):
    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, approach=(5e-3, 0.0, -2e-3))
    planner = _planner_knowing([site])
    scope = pip.scopeDevice()
    planner._scope_for_stage = lambda s: scope

    park_stage_pose = stage.globalPosition() + (PARK - scope.globalPosition())
    plan = planner.plan([MoveSpec(stage, park_stage_pose)])
    assert [m.device for m in _flat_moves(plan)] == [stage]


def test_a_stage_move_away_from_any_well_is_untouched(pip):
    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, approach=(90e-3, 90e-3, 90e-3))  # far from the stage pose
    planner = _planner_knowing([site])
    planner._scope_for_stage = lambda s: pip.scopeDevice()

    plan = planner.plan([MoveSpec(stage, np.array([1e-3, 0.0, 0.0]))])
    assert [m.device for m in _flat_moves(plan)] == [stage]


# ---------------------------------------------------------------------------
# Stage targets are checked against the stage's limits while planning
# ---------------------------------------------------------------------------


def test_an_out_of_limits_stage_target_fails_before_anything_moves(pip):
    from acq4.motion.planner import PlanningError

    class LimitedStage(MockStage):
        def checkGlobalLimits(self, pos, linear=False):
            if abs(pos[0]) > 10e-3:
                raise ValueError("x axis > limit")

    stage = LimitedStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, global_pos=(5e-3, 0.0, -2e-3), approach=(95e-3, 0.0, -2e-3))
    planner = _planner_knowing([site])
    pip.scopeDevice()._global_pos = PARK.copy()

    with pytest.raises(PlanningError, match="limits"):
        planner.plan([MoveSpec(pip, np.zeros(3), relative_to=site)])


# ---------------------------------------------------------------------------
# The pipette must follow the site to where the stage puts it
# ---------------------------------------------------------------------------


def test_interact_target_follows_the_site_after_the_stage_repositions(pip):
    """The park branch aimed at the site's pre-move position, short by the stage's travel."""
    stage = MockStage("Stage", global_pos=(0.0, 0.0, 0.0))
    site = _mobile_site(stage, global_pos=(5e-3, 0.0, -2e-3), approach=(40e-3, 0.0, -2e-3))
    planner = _planner_knowing([site])

    interact_local = np.asarray(site.interactLocalFor(pip), dtype=float)
    plan = planner.plan([MoveSpec(pip, interact_local, relative_to=site)])
    moves = _flat_moves(plan)

    stage_moves = [m for m in moves if m.device is stage]
    assert stage_moves, "the stage repositions the site"
    shift = stage_moves[-1].position - np.asarray(stage.globalPosition(), dtype=float)
    tube_after = np.asarray(site.mapToGlobal(interact_local), dtype=float) + shift

    np.testing.assert_array_almost_equal(moves[-1].position, tube_after)
