# Path generators and base motion planner for the Pipette device.
# High-level named-position logic (goHome, goApproach, etc.) lives in pipette.py;
# the global motion planner (acq4.motion) orchestrates multi-device movement.
from __future__ import annotations

from typing import TYPE_CHECKING, Union

import numpy as np
import pyqtgraph as pg
from acq4.util.future import future_wrap
from coorx import SRT3DTransform
from ... import getManager
from ...util.geometry import GeometryMotionPlanner, Plane

if TYPE_CHECKING:
    from .pipette import Pipette
    from ..Stage import Stage

RETRACTION_TO_AVOID_SAMPLE_TEAR = "retracting away from sample"
WAYPOINT_TO_AVOID_SAMPLE_TEAR = "waypoint to avoid sample tear"
MOVE_TO_DESTINATION = "final move to destination"
OBSTACLE_AVOIDANCE = "intermediate waypoint to avoid obstacles"
APPROACH_WAYPOINT = "approach waypoint"
SAFE_SPEED_WAYPOINT = "safe speed waypoint"
APPROACH_TO_CORRECT_FOR_HYSTERESIS = "hysteresis correction waypoint"


def qmatrix4x4_to_vispy_srt(qt_matrix):
    """Convert QMatrix4x4 to a SRT3DTransform."""
    np_matrix = np.array(qt_matrix.data()).reshape((4, 4))
    translation = np_matrix[:3, 3]

    rotation_scale_matrix = np_matrix[:3, :3]

    scale_x = np.linalg.norm(rotation_scale_matrix[:, 0])
    scale_y = np.linalg.norm(rotation_scale_matrix[:, 1])
    scale_z = np.linalg.norm(rotation_scale_matrix[:, 2])
    scale = np.array([scale_x, scale_y, scale_z])

    rotation_matrix = rotation_scale_matrix / scale

    def get_angle_axis():
        axes = [
            (1, 0, 0),
            (0, 1, 0),
            (0, 0, 1),
        ]

        for axis_idx, axis in enumerate(axes):
            if axis == (1, 0, 0):
                cos_val = rotation_matrix[1, 1]
                sin_val = -rotation_matrix[1, 2]
            elif axis == (0, 1, 0):
                cos_val = rotation_matrix[0, 0]
                sin_val = rotation_matrix[2, 0]
            else:
                cos_val = rotation_matrix[0, 0]
                sin_val = rotation_matrix[0, 1]

            angle = np.degrees(np.arctan2(sin_val, cos_val))

            if not np.isclose(angle, 0, atol=1e-5):
                return angle, axis

        return 0, (0, 0, 1)

    angle, axis = get_angle_axis()
    return SRT3DTransform(offset=translation, scale=scale, angle=angle, axis=axis)


class PipettePathGenerator:
    """Collection of methods for generating safe pipette paths.

    These methods are used by motion planners for avoiding obstacles, determining safe movement speeds, etc.

    The default implementation assumes an upright scope (requiring objective avoidance) and a thick sample
    (requiring slow, axial motion).
    """

    def __init__(self, pip: Pipette):
        self.pip = pip
        self.manipulator: Stage = pip.parentDevice()

    def safePath(self, globalStart, globalStop, speed, explanation=None):
        """Given global starting and stopping positions, return a list of global waypoints that avoid obstacles.

        Generally, movements are split into axes parallel and orthogonal to the pipette. When moving "inward", the
        parallel axis moves last. When moving "outward", the parallel axis moves first. This avoids most opportunities
        to collide with an objective lens / recording chamber, or to move laterally through tissue.

        If the start and stop positions are both near or inside the sample and have a lateral offset, then the pipette
        is first retracted away from the sample before proceeding to the final target.

        Any segments of the path that are inside or close to the sample are forced to the 'slow' speed.

        The returned path does _not_ include the starting position.
        """
        man = getManager()
        mod = man.getOrLoadModule("Visualize3D")
        # grab the visualizer for visualizing errors
        adapter = mod.window().findAdapter(lambda a: a.device == self.pip)
        explanation = explanation or MOVE_TO_DESTINATION
        globalStart = np.asarray(globalStart)
        globalStop = np.asarray(globalStop)
        path = [(globalStart, "", False, "")]

        # retract first if we are doing a lateral movement inside the sample
        lateralDist = np.linalg.norm(globalStop[1:] - globalStart[1:])
        if lateralDist > 1e-6:
            slowDepth = self.pip.approachDepth()
            canMoveLaterally = globalStart[2] > slowDepth or globalStop[2] > slowDepth
            if not canMoveLaterally:
                # need to retract first
                safePos = self.pip.positionAtDepth(slowDepth, start=globalStart)
                path.append((safePos, "slow", True, RETRACTION_TO_AVOID_SAMPLE_TEAR))
                # the rest of this method continues as if safePos is the starting point
                globalStart = safePos

        # ensure lateral motion occurs as far away from the recording chamber as possible
        localStart = self.pip.mapFromGlobal(path[-1][0])
        localStop = self.pip.mapFromGlobal(globalStop)

        # sort endpoints into inner (closer to sample) and outer (farther from sample)
        diff = localStop - localStart
        inward = diff[0] > 0
        innerPos, outerPos = (localStop, localStart) if inward else (localStart, localStop)

        # consider two possible waypoints, pick the one closer to the inner position
        pitch = self.pip.pitchRadians()
        localDirection = np.array([np.cos(pitch), 0, -np.sin(pitch)])
        if localDirection[0] == 0 or localDirection[2] == 0:
            raise ValueError(f"Invalid pipette pitch {pitch}; cannot compute approach waypoints.")
        waypoint1 = innerPos - localDirection * abs((diff[0] / localDirection[0]))
        waypoint2 = innerPos - localDirection * abs((diff[2] / localDirection[2]))
        dist1 = np.linalg.norm(waypoint1 - innerPos)
        dist2 = np.linalg.norm(waypoint2 - innerPos)
        waypoint = self.pip.mapToGlobal(waypoint1 if dist1 < dist2 else waypoint2)

        # break up the inner segment if part of it needs to be slower
        if inward:
            slowpath = self.enforceSafeSpeed(waypoint, globalStop, speed, explanation, linear=True)
            path += [(waypoint, speed, False, APPROACH_WAYPOINT)] + slowpath
        else:
            slowpath = self.enforceSafeSpeed(globalStart, waypoint, speed, APPROACH_WAYPOINT, linear=True)
            path += slowpath + [(globalStop, speed, False, explanation)]

        path = path[1:]  # trim off the start position
        for globalPos, speed, linear, stepName in path:
            if not np.isfinite(globalPos).all():
                raise ValueError(f"Invalid position {globalPos} for step '{stepName}' in path from {globalStart} to {globalStop}")
            try:
                # what global position should we ask the stage to move to in order for the pipette tip to reach globalPos
                manipulatorGlobalPos = self.pip._solveGlobalStagePosition(globalPos)
                # ask the stage to check whether this position is reachable
                self.manipulator.checkGlobalLimits(manipulatorGlobalPos, linear)
            except Exception as e:
                adapter.setPathError([globalStart] + [p[0] for p in path], failed_at=globalPos)
                raise ValueError(
                    f"Moving {self.pip} to '{stepName}' would be beyond the limits of its manipulator: {e}"
                ) from e
        adapter.setPath([globalStart] + [p[0] for p in path])
        return path

    def enforceSafeSpeed(self, start, stop, speed, explanation, linear):
        """Given global start/stop positions and a desired speed, return a path that reduces the speed for segments that
        are close to the sample.
        """
        if speed == "slow":
            # already slow; no need for extra steps
            return [(stop, speed, linear, explanation)]

        slowDepth = self.pip.approachDepth()
        startSlow = start[2] < slowDepth
        stopSlow = stop[2] < slowDepth
        if startSlow and stopSlow:
            # all slow
            return [(stop, "slow", linear, explanation)]
        elif not startSlow and not stopSlow:
            return [(stop, speed, linear, explanation)]
        else:
            waypoint = self.pip.positionAtDepth(slowDepth, start=start)
            if startSlow:
                return [(waypoint, "slow", linear, SAFE_SPEED_WAYPOINT), (stop, speed, linear, explanation)]
            else:
                return [(waypoint, speed, linear, SAFE_SPEED_WAYPOINT), (stop, "slow", linear, explanation)]

    def safeYZPosition(self, start, margin=2e-3):
        """Return a position to travel to, beginning from *start*, where the pipette may freely move in the local YZ
        plane without hitting obstacles (in particular the objective lens).
        """
        start = np.asarray(start)

        # where is the objective?
        scope = self.pip.scopeDevice()
        obj = scope.currentObjective
        objRadius = obj.radius
        assert objRadius is not None, "Can't determine safe location; radius of objective lens is not configured."
        localFocus = self.pip.mapFromGlobal(scope.globalPosition())

        # safe position along local x axis
        safeX = localFocus[0] - objRadius - margin

        # return starting position if it is already safe
        localStart = self.pip.mapFromGlobal(start)
        if localStart[0] < safeX:
            return start

        # best way to get to safe position
        dx = safeX - localStart[0]
        localDir = self.pip.localDirection()
        safePos = localStart + localDir * (dx / localDir[0])

        return self.pip.mapToGlobal(safePos)


class GeometryAwarePathGenerator(PipettePathGenerator):
    def __init__(self, pip: Pipette):
        super().__init__(pip)
        self._cachePrimer = self._primeCaches()
        self._cachePrimer.raiseErrors("error priming path planning caches")

    def _getPlanningContext(self):
        man = getManager()
        geometries = {}
        for dev in man.listInterfaces("OptomechDevice"):
            dev = man.getDevice(dev)
            # TODO what if one of these devices is actively moving?
            if dev == self.pip:
                continue
            geom = dev.getGeometry()
            if geom is not None:
                pg_xform = dev.globalPhysicalTransform().as_pyqtgraph()
                physical_xform = SRT3DTransform.from_pyqtgraph(
                    pg_xform,
                    from_cs=dev.geometryCacheKey,
                    to_cs="global",
                )
                geometries[geom] = physical_xform
        planner = GeometryMotionPlanner(geometries)
        pg_xform = self.pip.globalPhysicalTransform().as_pyqtgraph()
        from_pip_to_global = SRT3DTransform.from_pyqtgraph(
            pg_xform,
            from_cs=self.pip.geometryCacheKey,
            to_cs="global",
        )
        return planner, from_pip_to_global

    @future_wrap
    def _primeCaches(self, _future):
        try:
            man = getManager()
            while not man.isReady.wait(0.05):
                _future.checkStop()
            mod = man.getOrLoadModule("Visualize3D")
            while not mod.isReady.wait(0.05):
                _future.checkStop()
            viz = mod.window().findAdapter(lambda a: a.device == self.pip).pathSearchVisualizer()
            planner, from_pip_to_global = self._getPlanningContext()
            planner.make_convolved_obstacles(self.pip.getGeometry(), from_pip_to_global, viz)
            self.pip.logger.info("Finished priming path finding cache")
        except RuntimeError:
            self.pip.logger.exception("Blew up while attempting to prime path finding cache")

    def _planAroundSurface(self, pos):
        surface = self.pip.approachDepth()
        if pos[2] >= surface:
            return None
        return self.pip.positionAtDepth(surface, start=pos)

    def safePath(self, globalStart, globalStop, speed, explanation=None):
        self._cachePrimer.wait()

        boundaries = self.pip.getBoundaries()
        surface = self.pip.scopeDevice().getSurfaceDepth()
        boundaries += [Plane((0, 0, 1), (0, 0, surface), "sample surface")]
        prepend_path = append_path = []
        error_explanation = f"Move '{explanation}' could not be planned:"
        initial_waypoint = self._planAroundSurface(globalStart)
        if initial_waypoint is not None:
            prepend_path = [(initial_waypoint, "slow", False, RETRACTION_TO_AVOID_SAMPLE_TEAR)]
            globalStart = initial_waypoint
        final_waypoint = self._planAroundSurface(globalStop)
        if final_waypoint is not None:
            append_path = [(globalStop, "slow", False, explanation)]
            explanation = WAYPOINT_TO_AVOID_SAMPLE_TEAR
            globalStop = final_waypoint

        win = getManager().getOrLoadModule("Visualize3D").window()
        viz = win.findAdapter(lambda a: a.device == self.pip).pathSearchVisualizer()
        planner, from_pip_to_global = self._getPlanningContext()
        try:
            path = planner.find_path(
                self.pip.getGeometry(),
                from_pip_to_global,
                globalStart,
                globalStop,
                boundaries,
                visualizer=viz,
            )
        except Exception as e:
            viz.focus()
            raise ValueError(f"{error_explanation} {e}") from e
        if len(path) == 0:
            path = [(globalStop, speed, False, explanation)]
        else:
            path = [(waypoint, speed, False, OBSTACLE_AVOIDANCE) for waypoint in path]
            goal = path.pop()
            path += [(goal[0], speed, False, explanation)]
        path = prepend_path + path + append_path
        if viz:
            viz.endPath([globalStart] + [p[0] for p in path])
        return path


class PipetteMotionPlanner:
    """Base class for custom per-pipette motion planner overrides.

    Register subclasses in Pipette.motionPlanners to handle specific named positions with
    custom logic.  All standard named positions are handled by the go*() methods on Pipette
    which delegate to the global motion planner (acq4.motion).
    """

    def __init__(self, pip: Pipette, position: Union[np.ndarray, str], speed: float | str, **kwds):
        self.pip = pip
        self.position = position
        self.speed = speed
        self.kwds = kwds
        self.name = kwds.get("name", self._default_name())
        self.future = None
        self.safePath = self.pip.pathGenerator.safePath

    def _default_name(self):
        return "move"

    def move(self):
        """Execute the planned move and return a Future."""
        if self.future is not None:
            self.stop()
        self.future = self._move()
        return self.future

    def stop(self):
        if self.future is not None:
            self.future.stop()

    def _move(self):
        return self.pip._movePath(self.path(), name=f"{self.pip.name()} {self.name} path")

    def path(self):
        startPosGlobal = self.pip.globalPosition()
        if isinstance(self.position, str):
            endPosGlobal = self.pip.loadPosition(self.position)
        else:
            endPosGlobal = self.position
        return self.safePath(startPosGlobal, endPosGlobal, self.speed)
