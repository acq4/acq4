# DefaultMotionPlanner: the standard implementation of MotionPlanner.
# Handles InteractionSite interactions, pipette safe-path moves, and generic device moves.
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from acq4.devices.Pipette.planners import PipettePathGenerator
from .plan import AtomicMove, ParallelGroup, SequentialGroup
from .planner import MotionPlanner, PlanningError

if TYPE_CHECKING:
    from .plan import MovePlanStep
    from .spec import MoveSpec


class DefaultMotionPlanner(MotionPlanner):
    """Motion planner that captures the standard rules for pipette and interaction-site movements.

    Scope-park state is stored in _scope_context keyed by pipette name.  Custom planners can
    subclass and override individual _plan_* methods to compose different behaviors.
    """

    def __init__(self, config=None):
        super().__init__(config)
        # key: pip.name()  value: (scope_device, [original_pos, up_pos, park_pos])
        self._scope_context: dict[str, tuple] = {}

    def plan(self, specs: list["MoveSpec"]) -> SequentialGroup:
        steps = []
        for spec in specs:
            steps.append(self._plan_one(spec))
        return SequentialGroup(steps, "motion plan")

    def _plan_one(self, spec: "MoveSpec") -> "MovePlanStep":
        if self._is_interaction_site(spec.relative_to):
            return self._plan_interaction_approach(spec)
        if self._is_pipette(spec.device):
            return self._plan_pipette_move(spec)
        return self._plan_generic(spec)

    @staticmethod
    def _is_interaction_site(device) -> bool:
        """Duck-type check: does this device act as an InteractionSite?"""
        return device is not None and hasattr(device, "positions") and hasattr(device, "_parentStage")

    @staticmethod
    def _is_pipette(device) -> bool:
        """Duck-type check: does this device act as a Pipette with approach-depth semantics?"""
        return hasattr(device, "approachDepth") and hasattr(device, "scopeDevice")

    # ------------------------------------------------------------------
    # Case 1: InteractionSite interaction (approach + interact)
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: "MoveSpec") -> "MovePlanStep":
        """Generate the full approach→interact sequence for an InteractionSite target."""
        site = spec.relative_to
        pip = spec.device
        pip_name = pip.name()

        pos_config = site.positions.get(pip_name, {})
        if "interact global" not in pos_config:
            raise PlanningError(
                f"No interact position saved for {pip_name} at {site.name()}. "
                f"Use the InteractionSite UI to save approach and interact positions."
            )
        if "site global" not in pos_config:
            raise PlanningError(
                f"No approach position saved for {pip_name} at {site.name()}. "
                f"Use the InteractionSite UI to save the approach position."
            )

        approach_global = np.array(pos_config["site global"])
        interact_global = np.array(pos_config["interact global"])
        speed = spec.speed or "fast"

        steps = []

        # Scope park (if configured and not already parked for this pip)
        if "scopeParkPos" in site.config and pip_name not in self._scope_context:
            scope = pip.scopeDevice()
            original_pos = np.array(scope.globalPosition())
            park_pos = np.asarray(site.config["scopeParkPos"], dtype=float)
            up_pos = np.array([original_pos[0], original_pos[1], park_pos[2]])

            # Store forward path for reversal when pip goes home.
            self._scope_context[pip_name] = (scope, [original_pos, up_pos, park_pos])

            steps.append(
                SequentialGroup(
                    [
                        AtomicMove(scope, up_pos, speed, "scope up before approach"),
                        AtomicMove(scope, park_pos, speed, "scope to park position"),
                    ],
                    "scope park",
                )
            )

        # Move site stage and pip to safe position simultaneously
        site_stage = site._parentStage
        stage_delta = approach_global - np.array(site.globalPosition())
        site_stage_target = np.array(site_stage.globalPosition()) + stage_delta

        safe_pip_pos = np.array([0.0, 0.0, 10e-3])  # above sample while stage moves

        steps.append(
            ParallelGroup(
                [
                    AtomicMove(site_stage, site_stage_target, speed, f"move {site.name()} to approach"),
                    AtomicMove(pip, safe_pip_pos, "fast", "pip to safe height"),
                ],
                "approach preparation",
            )
        )

        # Pip to approach position
        steps.append(AtomicMove(pip, approach_global, speed, "pip to approach position"))

        # Pip to interact position
        steps.append(AtomicMove(pip, interact_global, speed, "pip to interact position"))

        return SequentialGroup(steps, f"interact with {site.name()}")

    # ------------------------------------------------------------------
    # Case 2: Pipette move (uses PipettePathGenerator for safe path)
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec") -> "MovePlanStep":
        """Generate safe waypoints for a pipette tip, then append scope unwind if needed."""
        pip = spec.device
        pip_name = pip.name()
        target = np.asarray(spec.position, dtype=float)
        speed = spec.speed or "fast"

        path_gen = PipettePathGenerator(pip)
        start = np.array(pip.globalPosition())
        waypoints = path_gen.safePath(start, target, speed)

        steps = [
            AtomicMove(pip, pos, spd, expl)
            for pos, spd, _linear, expl in waypoints
        ]

        # Scope unwind: append reversed park path after pip reaches home.
        if pip_name in self._scope_context:
            scope, forward_path = self._scope_context.pop(pip_name)
            # forward_path = [original, up, park]; return = [up, original]
            return_path = list(reversed(forward_path))[1:]
            scope_steps = [
                AtomicMove(scope, wp, "fast", "scope return")
                for wp in return_path
            ]
            steps.append(SequentialGroup(scope_steps, "scope unwind"))

        return SequentialGroup(steps, "pipette move")

    # ------------------------------------------------------------------
    # Case 3: Generic device
    # ------------------------------------------------------------------

    def _plan_generic(self, spec: "MoveSpec") -> "MovePlanStep":
        """Resolve relative positions and emit a single AtomicMove."""
        if not hasattr(spec.device, "moveToGlobal") and not hasattr(spec.device, "setGlobalPosition"):
            raise PlanningError(
                f"Device {spec.device!r} has no movement capability (no moveToGlobal or setGlobalPosition)."
            )

        if spec.relative_to is not None:
            global_pos = spec.relative_to.mapToGlobal(spec.position)
        else:
            global_pos = spec.position

        return AtomicMove(spec.device, global_pos, spec.speed or "fast", "move to target")
