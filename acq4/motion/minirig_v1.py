# MinirigV1MotionPlanner: motion planner for the minirig rig configuration.
# Adds scope-parking logic around InteractionSite interactions (cleaning wells,
# nucleus deposition tubes).  The scope path is reversed when the pipette goes home.
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .default_planner import DefaultMotionPlanner
from .plan import AtomicMove, SequentialGroup

if TYPE_CHECKING:
    from .plan import MovePlanStep
    from .spec import MoveSpec


class MinirigV1MotionPlanner(DefaultMotionPlanner):
    """Motion planner for the minirig rig.

    Extends DefaultMotionPlanner with scope-parking: when approaching an InteractionSite
    that has a scopeParkPos in its config, the scope is moved out of the way first and
    its path is stored so it can be reversed when the pipette goes home.

    Configure via MotionPlanner.class in the ACQ4 config file:
        MotionPlanner:
            class: acq4.motion.MinirigV1MotionPlanner
    """

    def __init__(self, config=None):
        super().__init__(config)
        # key: pip.name()
        # value: (scope_device, [original_pos, up_pos, park_pos])  — forward order
        self._scope_context: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Override: prepend scope park to the interaction approach sequence
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: "MoveSpec") -> "MovePlanStep":
        site = spec.relative_to
        pip = spec.device
        pip_name = pip.name()

        base = super()._plan_interaction_approach(spec)

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
    # Override: append scope unwind after pip reaches its destination
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec") -> "MovePlanStep":
        base = super()._plan_pipette_move(spec)

        pip_name = spec.device.name()
        if pip_name not in self._scope_context:
            return base

        scope, forward_path = self._scope_context.pop(pip_name)
        # forward_path = [original, up, park]; return path = [up, original]
        return_waypoints = list(reversed(forward_path))[1:]
        scope_steps = [
            AtomicMove(scope, wp, "fast", "scope return")
            for wp in return_waypoints
        ]
        return SequentialGroup(
            base.steps + [SequentialGroup(scope_steps, "scope unwind")],
            base.explanation,
        )
