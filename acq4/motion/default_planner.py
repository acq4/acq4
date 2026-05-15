# DefaultMotionPlanner: fairly generic motion planning for pipettes, interaction sites, and
# stages.  Any rig-specific sequencing belongs in a subclass.
from __future__ import annotations

import numpy as np

from .plan import AtomicMove, ParallelGroup, SequentialGroup
from .plan import MovePlanStep
from .planner import MotionPlanner, PlanningError
from .spec import MoveSpec

RETRACTION_TO_AVOID_SAMPLE_TEAR = "retracting away from sample"
WAYPOINT_TO_AVOID_SAMPLE_TEAR = "waypoint to avoid sample tear"
MOVE_TO_DESTINATION = "final move to destination"
OBSTACLE_AVOIDANCE = "intermediate waypoint to avoid obstacles"
APPROACH_WAYPOINT = "approach waypoint"
SAFE_SPEED_WAYPOINT = "safe speed waypoint"
APPROACH_TO_CORRECT_FOR_HYSTERESIS = "hysteresis correction waypoint"


class DefaultMotionPlanner(MotionPlanner):
    """Rig-agnostic motion planner.

    Dispatches each MoveSpec through one of three overridable cases:
      1. InteractionSite interaction  — approach + interact sequence
      2. Pipette move                 — delegates to pip.pathGenerator.safePath
      3. Generic device move          — single AtomicMove

    Scope parking, scope unwind, or any other rig-specific sequencing is intentionally
    absent here.  Subclass and override the relevant _plan_* method for rig-specific needs
    (see MinirigV1MotionPlanner for an example).
    """

    def plan(self, specs: list["MoveSpec"]) -> SequentialGroup:
        return SequentialGroup([self._plan_one(spec) for spec in specs], "motion plan")

    def _plan_one(self, spec: "MoveSpec") -> "MovePlanStep":
        if self._is_interaction_site(spec.relative_to):
            return self._plan_interaction_approach(spec)
        if self._is_pipette(spec.device):
            return self._plan_pipette_move(spec)
        return self._plan_generic(spec)

    @staticmethod
    def _is_interaction_site(device) -> bool:
        return device is not None and hasattr(device, "positions") and hasattr(device, "_parentStage")

    @staticmethod
    def _is_pipette(device) -> bool:
        return hasattr(device, "approachDepth") and hasattr(device, "pathGenerator")

    # ------------------------------------------------------------------
    # Case 1: InteractionSite interaction (approach → interact)
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: "MoveSpec") -> "MovePlanStep":
        """Generate the approach→interact sequence for an InteractionSite target."""
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

        # Compute where the site's stage must go so the site origin reaches approach_global.
        site_stage = site._parentStage
        stage_delta = approach_global - np.array(site.globalPosition())
        site_stage_target = np.array(site_stage.globalPosition()) + stage_delta

        safe_pip_pos = np.array([0.0, 0.0, 10e-3])

        return SequentialGroup(
            [
                ParallelGroup(
                    [
                        AtomicMove(site_stage, site_stage_target, speed, f"move {site.name()} to approach"),
                        AtomicMove(pip, safe_pip_pos, "fast", "pip to safe height"),
                    ],
                    "approach preparation",
                ),
                AtomicMove(pip, approach_global, speed, "pip to approach position"),
                AtomicMove(pip, interact_global, speed, "pip to interact position"),
            ],
            f"interact with {site.name()}",
        )

    # ------------------------------------------------------------------
    # Case 2: Pipette move (uses pip.pathGenerator for safe routing)
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: "MoveSpec") -> "MovePlanStep":
        """Generate safe waypoints for a pipette tip using the pipette's path generator."""
        pip = spec.device
        target = np.asarray(spec.position, dtype=float)
        speed = spec.speed or "fast"

        start = np.array(pip.globalPosition())
        waypoints = pip.pathGenerator.safePath(start, target, speed)

        steps = [
            AtomicMove(pip, pos, spd, expl)
            for pos, spd, _linear, expl in waypoints
        ]
        return SequentialGroup(steps, "pipette move")

    # ------------------------------------------------------------------
    # Case 3: Generic device
    # ------------------------------------------------------------------

    def _plan_generic(self, spec: "MoveSpec") -> "MovePlanStep":
        """Resolve relative positions and emit a single AtomicMove."""
        if not hasattr(spec.device, "moveToGlobalNoPlanning") and not hasattr(spec.device, "setGlobalPosition"):
            raise PlanningError(
                f"Device {spec.device!r} has no movement capability "
                f"(no moveToGlobalNoPlanning or setGlobalPosition)."
            )

        global_pos = (
            spec.relative_to.mapToGlobal(spec.position)
            if spec.relative_to is not None
            else spec.position
        )
        return AtomicMove(spec.device, global_pos, spec.speed or "fast", "move to target")
