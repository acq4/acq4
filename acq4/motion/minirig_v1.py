# MinirigV1MotionPlanner: extends DefaultMotionPlanner with microscope parking for cleaning wells.
from __future__ import annotations

import numpy as np

from .default_planner import DefaultMotionPlanner
from .plan import AtomicMove, SequentialGroup
from .plan import MovePlanStep
from .spec import MoveSpec


class MinirigV1MotionPlanner(DefaultMotionPlanner):
    """Motion planner for the v1 minirig rig.

    Extends DefaultMotionPlanner with "microscope parking": when approaching an InteractionSite
    that has a scopeParkPos in its config, the scope is moved out of the way before the pipette
    approaches.  The sequence is:

        1. Scope up (z-only, to park height) — scope clears objective before any lateral move
        2. Pipette retract to approach depth — pip exits tissue before scope moves laterally
        3. Scope to park position (lateral)
        4. Site stage to approach position (if the site is on a movable stage)
        5. Pipette to site approach position

    The reverse sequence runs when the pipette subsequently exits via any pipette move or
    interaction exit.

    Configure via MotionPlanner.class in the ACQ4 config file:
        MotionPlanner:
            class: "acq4.motion.MinirigV1MotionPlanner"
    """

    def __init__(self, config=None):
        super().__init__(config)
        # key: pip.name() -> (scope_device, [original_pos, up_pos, park_pos])  — forward order
        self._scope_context: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Override: full approach sequence with scope park
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        site = spec.relative_to
        pip = spec.device
        pip_name = pip.name()

        if "scopeParkPos" not in site.config or pip_name in self._scope_context:
            return super()._plan_interaction_approach(spec, name)

        scope = pip.scopeDevice()
        original_pos = np.array(scope.globalPosition())
        park_pos = np.asarray(site.config["scopeParkPos"], dtype=float)
        up_pos = np.array([original_pos[0], original_pos[1], park_pos[2]])

        self._scope_context[pip_name] = (scope, [original_pos, up_pos, park_pos])

        speed = spec.speed or "fast"
        pip_start = np.array(pip.globalPosition())

        # scope up (z-only) — must happen before any lateral scope movement
        steps = [AtomicMove(scope, up_pos, speed, "scope up before park")]

        # pipette retract to approach depth — pip exits tissue before scope goes lateral
        pip_safe = pip.positionAtDepth(pip.approachDepth(), start=pip_start)
        if pip_safe[2] > pip_start[2]:
            steps.append(AtomicMove(pip, pip_safe, speed, "pip retract before scope park"))
            pip_start = pip_safe

        # pipette goes home
        steps.append(AtomicMove(pip, pip.homePosition(), speed, "pipette home before scope park"))

        # scope lateral to park position
        steps.append(AtomicMove(scope, park_pos, speed, "scope to park position"))

        # site stage to approach position (if on a movable stage)
        approach_global = np.array(site.approachGlobal(pip))
        site_spec = site.approachMoveSpec(pip, speed=speed)
        if site_spec is not None:
            steps.append(self._plan_generic(site_spec, f"position {site.name()}"))

        # pipette to approach position (safe path from current retracted position)
        kw = spec.kwargs
        pip_to_approach = self._safe_path(pip, pip_start, approach_global, speed)
        steps.extend(
            AtomicMove(pip, pos, spd, expl, {'linear': lin, **kw})
            for pos, spd, lin, expl in pip_to_approach
        )

        # pipette into site (only when going inside and approach is saved)
        going_inside = not np.allclose(spec.position, 0)
        if going_inside and site.hasApproachPosition(pip):
            # spec.position is relative to LIVE site, so no need to add site_delta
            target_global = np.array(site.mapToGlobal(spec.position))
            steps.append(
                AtomicMove(pip, target_global, speed, "pipette into site", {'linear': True, **kw})
            )

        return SequentialGroup(steps, name or f"approach {site.name()}")

    # ------------------------------------------------------------------
    # Shared helper: append scope unwind steps to a plan
    # ------------------------------------------------------------------

    def _append_scope_unwind(self, base: "MovePlanStep", pip_name: str) -> "MovePlanStep":
        if pip_name not in self._scope_context:
            return base
        scope, forward_path = self._scope_context.pop(pip_name)
        # forward_path = [original, up, park]; return path skips park (already there)
        return_waypoints = list(reversed(forward_path))[1:]
        scope_steps = [AtomicMove(scope, wp, "fast", "scope return") for wp in return_waypoints]
        return SequentialGroup(
            base.steps + [SequentialGroup(scope_steps, "scope unwind")],
            base.explanation,
        )

    # ------------------------------------------------------------------
    # Override: append scope unwind when exiting via approach waypoint
    # ------------------------------------------------------------------

    def _plan_interaction_exit(
        self, spec: "MoveSpec", name: str = "", containing_site=None
    ) -> "MovePlanStep":
        base = super()._plan_interaction_exit(spec, name, containing_site)
        return self._append_scope_unwind(base, spec.device.name())

    # ------------------------------------------------------------------
    # Override: append scope unwind on direct pipette moves (fallback)
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        base = super()._plan_pipette_move(spec, name)
        return self._append_scope_unwind(base, spec.device.name())
