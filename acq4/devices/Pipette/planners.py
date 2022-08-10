from __future__ import annotations
import numpy as np
from acq4.util.future import MultiFuture

import typing
if typing.TYPE_CHECKING:
    from .pipette import Pipette


def defaultMotionPlanners():
    return {
        'home': HomeMotionPlanner,
        'search': SearchMotionPlanner,
        'aboveTarget': AboveTargetMotionPlanner,
        'approach': ApproachMotionPlanner,
        'target': TargetMotionPlanner,
        'idle': IdleMotionPlanner,
    }


class PipettePathGenerator:
    """Collection of methods for generating safe pipette paths.

    These methods are used by motion planners for avoiding obstacles, determining safe movement speeds, etc.

    The default implementation assumes an upright scope (requiring objective avoidance) and a thick sample
    (requiring slow, axial motion).
    """
    def __init__(self, pip: Pipette):
        self.pip = pip

    def safePath(self, globalStart, globalStop, speed):
        """Given global starting and stopping positions, return a list of global waypoints that avoid obstacles.

        Generally, movements are split into axes parallel and orthogonal to the pipette. When moving "inward", the
        parallel axis moves last. When moving "outward", the parallel axis moves first. This avoids most opportunities
        to collide with an objective lens / recording chamber, or to move laterally through tissue.

        If the start and stop positions are both near or inside the sample and have a lateral offset, then the pipette
        is first retracted away from the sample before proceeding to the final target.

        Any segments of the path that are inside or close to the sample are forced to the 'slow' speed.

        The returned path does _not_ include the starting position.
        """
        globalStart = np.asarray(globalStart)
        globalStop = np.asarray(globalStop)
        path = [(globalStart,)]

        # retract first if we are doing a lateral movement inside the sample
        lateralDist = np.linalg.norm(globalStop[1:] - globalStart[1:])
        if lateralDist > 1e-6:
            slowDepth = self.pip.approachDepth()
            canMoveLaterally = globalStart[2] > slowDepth or globalStop[2] > slowDepth
            if not canMoveLaterally:
                # need to retract first
                safePos = self.pip.positionAtDepth(slowDepth, start=globalStart)
                path.append((safePos, 'slow', True))
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
        waypoint1 = innerPos - localDirection * abs((diff[0] / localDirection[0]))
        waypoint2 = innerPos - localDirection * abs((diff[2] / localDirection[2]))
        dist1 = np.linalg.norm(waypoint1 - innerPos)
        dist2 = np.linalg.norm(waypoint2-innerPos)
        waypoint = self.pip.mapToGlobal(waypoint1 if dist1 < dist2 else waypoint2)

        # break up the inner segment if part of it needs to be slower
        if inward:
            slowpath = self.enforceSafeSpeed(waypoint, globalStop, speed, linear=True)
            path += [(waypoint, speed, False)] + slowpath
        else:
            slowpath = self.enforceSafeSpeed(globalStart, waypoint, speed, linear=True)
            path += slowpath + [(globalStop, speed, False)]

        for step in path:
            assert np.isfinite(step[0]).all()
        return path[1:]

    def enforceSafeSpeed(self, start, stop, speed, linear):
        """Given global start/stop positions and a desired speed, return a path that reduces the speed for segments that
        are close to the sample.
        """
        if speed == 'slow':
            # already slow; no need for extra steps
            return [(stop, speed, linear)]

        slowDepth = self.pip.approachDepth()
        startSlow = start[2] < slowDepth
        stopSlow = stop[2] < slowDepth
        if startSlow and stopSlow:
            # all slow
            return [(stop, 'slow', linear)]
        elif not startSlow and not stopSlow:
            return [(stop, speed, linear)]
        else:
            waypoint = self.pip.positionAtDepth(slowDepth, start=start)
            if startSlow:
                return [(waypoint, 'slow', linear), (stop, speed, linear)]
            else:
                return [(waypoint, speed, linear), (stop, 'slow', linear)]

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


class PipetteMotionPlanner:
    """Pipette motion planners are responsible for safely executing movement of the pipette and (optionally) the microscope
     focus to specific locations.

    For example, moving to a pipette search position involves setting the focus to a certain height, followed by inserting
    the pipette tip diagonally near the
    """
    def __init__(self, pip: Pipette, position: np.ndarray, speed: float, **kwds):
        self.pip = pip
        self.position = position
        self.speed = speed
        self.kwds = kwds

        self.future = None

        # wrap safePath for convenience
        self.safePath = self.pip.pathGenerator.safePath

    def move(self):
        """Move the pipette to the requested named position and return a Future 
        """
        if self.future is not None:
            self.stop()

        self.future = self._move()
        return self.future

    def stop(self):
        if self.future is not None:
            self.future.stop()

    def _move(self):
        path = self.path()
        return self.pip._movePath(path)

    def path(self):
        raise NotImplementedError()


class HomeMotionPlanner(PipetteMotionPlanner):
    """Extract pipette tip diagonally, then move to home position.
    """
    def path(self):
        manipulator = self.pip.parentDevice()
        manipulatorHome = manipulator.homePosition()
        assert manipulatorHome is not None, "No home position defined for %s" % manipulator.name()
        # how much should the pipette move in global coordinates
        globalMove = np.asarray(manipulatorHome) - np.asarray(manipulator.globalPosition())

        startPosGlobal = self.pip.globalPosition()
        # where should the pipette tip end up in global coordinates
        endPosGlobal = np.asarray(startPosGlobal) + globalMove

        path = self.safePath(startPosGlobal, endPosGlobal, self.speed)
        return path


class SearchMotionPlanner(PipetteMotionPlanner):
    """Focus the microscope 2mm above the surface, then move the electrode 
    tip to 500um below the focal point of the microscope. 

    This position is used when searching for new electrodes.

    Set *distance* to adjust the search position along the pipette's x-axis. Positive values
    move the tip farther from the microscope center to reduce the probability of collisions.
    Negative values move the pipette past the center of the microscope to improve the
    probability of seeing the tip immediately. 
    """
    def _move(self):
        pip = self.pip
        speed = self.speed
        distance = self.kwds.get('distance', 0)

        # Bring focus to 2mm above surface (if needed)
        scope = pip.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        if surfaceDepth is None:
            raise Exception("Cannot determine search position; surface depth is not defined.")
        searchDepth = surfaceDepth + pip._opts['searchHeight']

        cam = pip.imagingDevice()
        focusDepth = cam.getFocusDepth()

        # move scope such that camera will be focused at searchDepth
        if focusDepth < searchDepth:
            scopeFocus = scope.getFocusDepth()
            fut = scope.setFocusDepth(scopeFocus + searchDepth - focusDepth)
            # wait for objective to lift before starting pipette motion
            fut.wait(updates=True)

        # Here's where we want the pipette tip in global coordinates:
        globalCenter = cam.globalCenterPosition('roi')
        globalCenter[2] += pip._opts['searchTipHeight'] - pip._opts['searchHeight']

        # adjust for distance argument:
        globalTarget = globalCenter + pip.globalDirection() * distance

        path = self.safePath(pip.globalPosition(), globalTarget, speed)

        return pip._movePath(path)


class ApproachMotionPlanner(PipetteMotionPlanner):
    def path(self):
        pip = self.pip
        approachDepth = pip.approachDepth()
        approachPosition = pip.positionAtDepth(approachDepth, start=pip.targetPosition())
        path = self.safePath(pip.globalPosition(), approachPosition, self.speed)
        return path


class TargetMotionPlanner(PipetteMotionPlanner):
    def path(self):
        start = self.pip.globalPosition()
        stop = self.pip.targetPosition()
        return self.safePath(start, stop, self.speed)


class AboveTargetMotionPlanner(PipetteMotionPlanner):
    """Move the pipette tip to be centered over the target in x/y, and 100 um above
    the sample surface in z. 

    This position is used to recalibrate the pipette immediately before going to approach.
    """
    def _move(self):
        pip = self.pip
        speed = self.speed

        scope = pip.scopeDevice()
        waypoint1, waypoint2 = self.aboveTargetPath()

        path = self.safePath(pip.globalPosition(), waypoint1, speed)
        path.append((waypoint2, 'slow', True))
        pfut = pip._movePath(path)
        sfut = scope.setGlobalPosition(waypoint2)

        return MultiFuture([pfut, sfut])

    def aboveTargetPath(self):
        """Return the path to the "above target" recalibration position.

        The path has 2 waypoints:

        1. 100 um away from the second waypoint, on a diagonal approach. This is meant to normalize the hysteresis
           at the second waypoint. 
        2. This position is centered on the target, a small distance above the sample surface.
        """
        pip = self.pip
        target = pip.targetPosition()

        # will recalibrate 50 um above surface
        scope = pip.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        waypoint2 = np.array(target)
        waypoint2[2] = surfaceDepth + 50e-6

        # Need to arrive at this point via approach angle to correct for hysteresis
        waypoint1 = waypoint2 + pip.globalDirection() * -100e-6

        return waypoint1, waypoint2


class IdleMotionPlanner(PipetteMotionPlanner):
    """Move the electrode tip to the outer edge of the recording chamber, 1mm above the sample surface.

    NOTE: this method assumes that (0, 0) in global coordinates represents the center of the recording
    chamber.
    """
    def _move(self):
        pip = self.pip
        speed = self.speed

        scope = pip.scopeDevice()
        surface = scope.getSurfaceDepth()
        if surface is None:
            raise Exception("Surface depth has not been set.")

        # we want to land 1 mm above sample surface
        idleDepth = surface + pip._opts['idleHeight']

        # If the tip is below idle depth, bring it up along the axis of the electrode.
        pos = pip.globalPosition()
        if pos[2] < idleDepth:
            pip.advance(idleDepth, speed)

        # From here, move directly to idle position
        angle = pip.yawRadians()
        ds = pip._opts['idleDistance']  # move to 7 mm from center
        globalIdlePos = -ds * np.cos(angle), -ds * np.sin(angle), idleDepth
        
        return pip._moveToGlobal(globalIdlePos, speed)
