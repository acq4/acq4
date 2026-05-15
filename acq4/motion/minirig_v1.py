# MinirigV1MotionPlanner: motion planner for the minirig rig configuration.
# Adds scope-parking logic around InteractionSite interactions (cleaning wells,
# nucleus deposition tubes).  The scope path is reversed when the pipette exits.
from __future__ import annotations

import numpy as np

from .default_planner import DefaultMotionPlanner
from .plan import AtomicMove, SequentialGroup
from .plan import MovePlanStep
from .spec import MoveSpec


class MinirigV1MotionPlanner(DefaultMotionPlanner):
    """Motion planner for the minirig rig.

    Extends DefaultMotionPlanner with scope-parking: when approaching an InteractionSite
    that has a scopeParkPos in its config, the scope is moved out of the way first and
    its path is stored so it can be reversed when the pipette exits.

    Configure via MotionPlanner.class in the ACQ4 config file:
        MotionPlanner:
            class: acq4.motion.MinirigV1MotionPlanner
    """

    def __init__(self, config=None):
        super().__init__(config)
        # key: pip.name() -> (scope_device, [original_pos, up_pos, park_pos])  — forward order
        self._scope_context: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Override: prepend scope park to the interaction approach sequence
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        site = spec.relative_to
        pip = spec.device
        pip_name = pip.name()

        base = super()._plan_interaction_approach(spec, name)

        if "scopeParkPos" not in site.config or pip_name in self._scope_context:
            return base

        scope = pip.scopeDevice()
        original_pos = np.array(scope.globalPosition())
        park_pos = np.asarray(site.config["scopeParkPos"], dtype=float)
        up_pos = np.array([original_pos[0], original_pos[1], park_pos[2]])

        self._scope_context[pip_name] = (scope, [original_pos, up_pos, park_pos])

        scope_park = SequentialGroup(
            [
                AtomicMove(scope, up_pos, spec.speed or "fast", "scope up before approach"),
                AtomicMove(scope, park_pos, spec.speed or "fast", "scope to park position"),
            ],
            "scope park",
        )
        return SequentialGroup([scope_park] + base.steps, base.explanation)

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

    def _plan_interaction_exit(self, spec: "MoveSpec", name: str = "", containing_site=None) -> "MovePlanStep":
        base = super()._plan_interaction_exit(spec, name, containing_site)
        return self._append_scope_unwind(base, spec.device.name())

    # ------------------------------------------------------------------
    # Override: append scope unwind on direct pipette moves (fallback)
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec", name: str = "") -> "MovePlanStep":
        base = super()._plan_pipette_move(spec, name)
        return self._append_scope_unwind(base, spec.device.name())
