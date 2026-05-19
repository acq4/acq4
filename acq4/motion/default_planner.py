# DefaultMotionPlanner: generic motion planning for pipettes, interaction sites, and stages.
# Any rig-specific sequencing belongs in a subclass.
from __future__ import annotations

import numpy as np

from acq4 import getManager
from acq4.util.future import future_wrap
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
    """Generic, likely-safe motion planner. Assumes an upright scope and thick sample tissue.

    Three dispatch cases:
      1. InteractionSite interaction  — enforce approach->interact order; add approach waypoint on exit
      2. Pipette move                 — avoid objective, move slowly near sample surface
      3. Generic device move          — single atomic move

    Path generation for pipette moves lives on this class (see _safe_path and friends).
    GeometryAwareMotionPlanner is a subclass that overrides _safe_path with obstacle avoidance.

    Sites may set ``directAccess: true`` in their config to skip approach-waypoint enforcement.
    Use this for the recording chamber.  Clean wells and nucleus tubes should leave it unset.

    Override the relevant ``_plan_*`` methods for rig-specific behavior (see MinirigV1MotionPlanner).
    """

    def collect_devices(self, plan) -> set:
        devices = super().collect_devices(plan)
        # scope position must be stable while pipette path-finding runs
        for dev in list(devices):
            if self._is_pipette(dev):
                scope = dev.scopeDevice()
                if scope is not None:
                    devices.add(scope)
        return devices


    def plan(self, specs, name=""):
        # TODO can this be parallel? (requires at least thread-safe locking)
        return SequentialGroup([self._plan_one(spec, name) for spec in specs], name or "motion plan")

    def _plan_one(self, spec: MoveSpec, name: str = "") -> MovePlanStep:
        if self._is_interaction_site(spec.relative_to):
            return self._plan_interaction_approach(spec, name)
        if self._is_pipette(spec.device):
            containing_site = self._find_containing_site(spec.device)
            if containing_site is not None:
                return self._plan_interaction_exit(spec, name, containing_site)
            return self._plan_pipette_move(spec, name)
        return self._plan_generic(spec, name)

    @staticmethod
    def _is_interaction_site(device) -> bool:
        return (
            device is not None and hasattr(device, "positions") and hasattr(device, "_parentStage")
        )

    @staticmethod
    def _is_pipette(device) -> bool:
        return hasattr(device, "approachDepth") and hasattr(device, "positionAtDepth")

    def _find_containing_site(self, pip):
        """Return the first interaction site that geometrically contains the pipette tip, or None.

        Queries the Manager for all known devices.  Override in tests to inject a mock result.
        """
        try:
            man = getManager()
        except Exception:
            return None
        pip_pos = pip.globalPosition()
        for dev_name in man.listDevices():
            dev = man.getDevice(dev_name)
            if self._is_interaction_site(dev) and dev.containsPoint(pip_pos):
                return dev
        return None

    # ------------------------------------------------------------------
    # Case 1a: InteractionSite approach
    # ------------------------------------------------------------------

    def _plan_interaction_approach(self, spec: MoveSpec, name: str = "") -> MovePlanStep:
        """Generate waypoints to reach an InteractionSite target.

        Approach = site origin (site.globalPosition()).  If the site is on a movable stage,
        a parallel group repositions the stage while the pipette rises to a safe height.
        Sites with ``directAccess: true`` skip approach-waypoint enforcement.
        """
        site = spec.relative_to
        pip = spec.device
        speed = spec.speed or "fast"

        # approach_global is the calibrated site-origin position in global coords.
        # For fixed sites this equals site.globalPosition(); for movable sites it may differ.
        approach_global = np.array(site.approachGlobal(pip))
        # site_delta is how far the site will shift when repositioned.
        # All site-relative positions must be offset by this to stay in the right place.
        site_delta = approach_global - np.array(site.globalPosition())

        direct_access = site.config.get("directAccess", False)
        going_inside = not np.allclose(spec.position, 0)
        # target_global is computed from the current transform then corrected for site movement.
        target_global = np.array(site.mapToGlobal(spec.position)) + site_delta if going_inside else approach_global

        start = np.array(pip.globalPosition())

        # If the site has a movable stage, reposition it (and raise pip) before approaching.
        site_spec = site.approachMoveSpec(pip, speed=speed)
        prefix_steps = []
        if site_spec is not None:
            safe_z = pip.positionAtDepth(pip.approachDepth(), start=start)
            prefix_steps = [
                ParallelGroup(
                    [
                        self._plan_generic(site_spec, f"position {site.name()}"),
                        AtomicMove(pip, safe_z, speed, "pip to safe height"),
                    ],
                    f"reposition {site.name()} and lift pip",
                )
            ]
            start = safe_z

        if not going_inside or direct_access:
            final = approach_global if not going_inside else target_global
            waypoints = self._safe_path(pip, start, final, speed)
            steps = [AtomicMove(pip, pos, spd, expl) for pos, spd, _, expl in waypoints]
            return SequentialGroup(prefix_steps + steps, name or f"approach {site.name()}")

        to_approach = self._safe_path(pip, start, approach_global, speed)
        to_approach_steps = [AtomicMove(pip, pos, spd, expl) for pos, spd, _, expl in to_approach]
        interact_step = AtomicMove(pip, target_global, speed, name or f"interact with {site.name()}")
        return SequentialGroup(
            prefix_steps + to_approach_steps + [interact_step],
            name or f"interact with {site.name()}",
        )

    # ------------------------------------------------------------------
    # Case 1b: InteractionSite exit
    # ------------------------------------------------------------------

    def _plan_interaction_exit(self, spec: MoveSpec, name: str = "", containing_site=None) -> MovePlanStep:
        """Exit a restricted-access site via its approach position before moving to the target."""
        pip = spec.device
        approach_global = np.array(containing_site.globalPosition())
        speed = spec.speed or "fast"

        exit_step = AtomicMove(pip, approach_global, speed, f"exit site before {name or 'move'}")
        target = np.asarray(spec.position, dtype=float)
        rest_waypoints = self._safe_path(pip, approach_global, target, speed)
        rest_steps = [AtomicMove(pip, pos, spd, expl) for pos, spd, _, expl in rest_waypoints]
        return SequentialGroup(
            [exit_step] + rest_steps,
            name or "exit site and move to target",
        )

    # ------------------------------------------------------------------
    # Case 2: Pipette move
    # ------------------------------------------------------------------

    def _plan_pipette_move(self, spec: MoveSpec, name: str = "") -> MovePlanStep:
        """Generate safe waypoints using the planner's path generator."""
        pip = spec.device
        target = np.asarray(spec.position, dtype=float)
        speed = spec.speed or "fast"
        start = np.array(pip.globalPosition())
        waypoints = self._safe_path(pip, start, target, speed)
        steps = [AtomicMove(pip, pos, spd, expl) for pos, spd, _linear, expl in waypoints]
        return SequentialGroup(steps, name or "pipette move")

    # ------------------------------------------------------------------
    # Case 3: Generic device
    # ------------------------------------------------------------------

    def _plan_generic(self, spec: MoveSpec, name: str = "") -> MovePlanStep:
        """Resolve relative position and emit a single AtomicMove."""
        global_pos = (
            spec.relative_to.mapToGlobal(spec.position)
            if spec.relative_to is not None
            else spec.position
        )
        return AtomicMove(spec.device, global_pos, spec.speed or "fast", name or "move to target")

    # ------------------------------------------------------------------
    # Path generation — override in subclasses for geometry-aware routing
    # ------------------------------------------------------------------

    def _safe_path(self, pip, globalStart, globalStop, speed, explanation=None):
        """Return a list of (position, speed, linear, explanation) waypoints from start to stop.

        Assumes upright scope (objective avoidance) and thick sample (slow axial motion near tissue).
        Override in subclasses (e.g. GeometryAwareMotionPlanner) for full obstacle avoidance.
        The returned path does not include the starting position.
        """
        explanation = explanation or MOVE_TO_DESTINATION
        globalStart = np.asarray(globalStart)
        globalStop = np.asarray(globalStop)
        path = [(globalStart, "", False, "")]

        # retract first if we are doing a lateral movement inside the sample
        lateralDist = np.linalg.norm(globalStop[1:] - globalStart[1:])
        if lateralDist > 1e-6:
            slowDepth = pip.approachDepth()
            canMoveLaterally = globalStart[2] > slowDepth or globalStop[2] > slowDepth
            if not canMoveLaterally:
                safePos = pip.positionAtDepth(slowDepth, start=globalStart)
                path.append((safePos, "slow", True, RETRACTION_TO_AVOID_SAMPLE_TEAR))
                globalStart = safePos

        # ensure lateral motion occurs as far away from the recording chamber as possible
        localStart = pip.mapFromGlobal(path[-1][0])
        localStop = pip.mapFromGlobal(globalStop)

        diff = localStop - localStart
        inward = diff[0] > 0
        innerPos, outerPos = (localStop, localStart) if inward else (localStart, localStop)

        pitch = pip.pitchRadians()
        localDirection = np.array([np.cos(pitch), 0, -np.sin(pitch)])
        if localDirection[0] == 0 or localDirection[2] == 0:
            raise ValueError(f"Invalid pipette pitch {pitch}; cannot compute approach waypoints.")
        waypoint1 = innerPos - localDirection * abs((diff[0] / localDirection[0]))
        waypoint2 = innerPos - localDirection * abs((diff[2] / localDirection[2]))
        dist1 = np.linalg.norm(waypoint1 - innerPos)
        dist2 = np.linalg.norm(waypoint2 - innerPos)
        waypoint = pip.mapToGlobal(waypoint1 if dist1 < dist2 else waypoint2)

        if inward:
            slowpath = self._enforce_safe_speed(pip, waypoint, globalStop, speed, explanation, linear=True)
            path += [(waypoint, speed, False, APPROACH_WAYPOINT)] + slowpath
        else:
            slowpath = self._enforce_safe_speed(pip, globalStart, waypoint, speed, APPROACH_WAYPOINT, linear=True)
            path += slowpath + [(globalStop, speed, False, explanation)]

        path = path[1:]
        full_path = [globalStart] + [p[0] for p in path]
        for globalPos, spd, linear, stepName in path:
            if not np.isfinite(globalPos).all():
                raise ValueError(
                    f"Invalid position {globalPos} for step '{stepName}' in path from {globalStart} to {globalStop}"
                )
            try:
                manipulatorGlobalPos = pip._solveGlobalStagePosition(globalPos)
                pip.parentDevice().checkGlobalLimits(manipulatorGlobalPos, linear)
            except Exception as e:
                self._on_path_error(pip, full_path, globalPos)
                raise ValueError(
                    f"Moving {pip} to '{stepName}' would be beyond the limits of its manipulator: {e}"
                ) from e
        self._on_path_computed(pip, full_path)
        return path

    def _on_path_computed(self, pip, full_path):
        """Notify visualization after a valid path is computed. Override to suppress in tests."""
        try:
            man = getManager()
            mod = man.getOrLoadModule("Visualize3D")
            adapter = mod.window().findAdapter(lambda a: a.device == pip)
            adapter.setPath(full_path)
        except Exception:
            pass

    def _on_path_error(self, pip, full_path, failed_at):
        """Notify visualization when a path step fails limit checks. Override to suppress in tests."""
        try:
            man = getManager()
            mod = man.getOrLoadModule("Visualize3D")
            adapter = mod.window().findAdapter(lambda a: a.device == pip)
            adapter.setPathError(full_path, failed_at=failed_at)
        except Exception:
            pass

    def _enforce_safe_speed(self, pip, start, stop, speed, explanation, linear):
        """Return path segments with speed reduced for portions near the sample surface."""
        if speed == "slow":
            return [(stop, speed, linear, explanation)]
        slowDepth = pip.approachDepth()
        startSlow = start[2] < slowDepth
        stopSlow = stop[2] < slowDepth
        if startSlow and stopSlow:
            return [(stop, "slow", linear, explanation)]
        if not startSlow and not stopSlow:
            return [(stop, speed, linear, explanation)]
        waypoint = pip.positionAtDepth(slowDepth, start=start)
        if startSlow:
            return [
                (waypoint, "slow", linear, SAFE_SPEED_WAYPOINT),
                (stop, speed, linear, explanation),
            ]
        return [
            (waypoint, speed, linear, SAFE_SPEED_WAYPOINT),
            (stop, "slow", linear, explanation),
        ]

    def _safe_yz_position(self, pip, start, margin=2e-3):
        """Return a position where the pipette can freely move in its local YZ plane."""
        start = np.asarray(start)
        scope = pip.scopeDevice()
        obj = scope.currentObjective
        objRadius = obj.radius
        assert objRadius is not None, "Can't determine safe location; objective radius not configured."
        localFocus = pip.mapFromGlobal(scope.globalPosition())
        safeX = localFocus[0] - objRadius - margin
        localStart = pip.mapFromGlobal(start)
        if localStart[0] < safeX:
            return start
        dx = safeX - localStart[0]
        localDir = pip.localDirection()
        safePos = localStart + localDir * (dx / localDir[0])
        return pip.mapToGlobal(safePos)


