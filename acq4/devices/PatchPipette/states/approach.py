from __future__ import annotations

from threading import Lock

import numpy as np

from acq4 import getManager
from acq4.util import ptime
from acq4.util.debug import printExc
from acq4.util.future import future_wrap
from acq4.util.imaging.sequencer import run_image_sequence
from ._base import PatchPipetteState
from .cell_detect import CellDetectAnalysis


class ApproachState(PatchPipetteState):
    """State for approaching a target.

    Parameters
    ----------
    autoAdvance : bool
        If True, automatically advance the pipette (default False)
    advanceContinuous : bool
        Whether to advance the pipette with continuous motion or in small steps (default True)
    advanceStepInterval : float
        Time duration (seconds) to wait between steps when advanceContinuous=False(default 0.1)
    advanceStepDistance : float
        Distance (m) per step when advanceContinuous=False (default 1 µm)
    minDetectionDistance : float
        Minimum distance (m) from target before cell detection can be considered (default 15 µm)
    aboveSurfaceSpeed : float
        Speed (m/s) to advance the pipette when above the surface (default 20 um/s)
    belowSurfaceSpeed : float
        Speed (m/s) to advance the pipette when below the surface (default 5 um/s)
    obstacleDetection : bool
        If True, sidestep obstacles (default False)
    obstacleRecoveryTime : float
        Time (s) allowed after retreating from an obstacle to let resistance to return to normal (default 1 s)
    obstacleResistanceThreshold : float
        Resistance (Ohm) threshold above the initial resistance measurement for detecting an obstacle (default 1 MOhm)
    sidestepLateralDistance : float
        Distance (m) to sidestep an obstacle (default 10 µm)
    sidestepBackupDistance : float
        Distance (m) to backup before sidestepping (default 10 µm)
    sidestepPassDistance : float
        Distance (m) to pass an obstacle (default 20 µm)
    takeACellfie : bool
        Whether to take a z-stack of the cell at the start of this state (default True)
    cellfieHeight : float
        Vertical distance (m) of the initial z-stack (default 30 µm)
    cellfieStep : float
        Vertical distance (m) between z-stack slices (default 1 µm)
    cellfiePipetteClearance : float
        Minimum distance (m) between target and pipette tip in which to allow the z-stack to be taken (default 100 µm)
    pipetteRecalibrateDistance : float
        Distance between pipette and target at which to pause and recalibrate the pipette offset
    pipetteRecalibrationMaxChange : float
        Maximum distance allowed for an automatic pipette tip position update
    """

    stateName = "approach"

    _parameterDefaultOverrides = {
        "initialClampMode": "VC",
        "initialVCHolding": 0,
        "initialTestPulseEnable": True,
        "fallbackState": "bath",
    }
    _parameterTreeConfig = {
        "autoAdvance": {"default": False, "type": "bool"},
        "advanceContinuous": {"default": True, "type": "bool"},
        "advanceStepInterval": {"default": 0.1, "type": "float", "suffix": "s"},
        "advanceStepDistance": {"default": 1e-6, "type": "float", "suffix": "m"},
        "maxAdvanceDistancePastTarget": {"default": 10e-6, "type": "float", "suffix": "m"},
        "minDetectionDistance": {"default": 15e-6, "type": "float", "suffix": "m"},
        "aboveSurfaceSpeed": {"default": 20e-6, "type": "float", "suffix": "m/s"},
        "belowSurfaceSpeed": {"default": 5e-6, "type": "float", "suffix": "m/s"},
        "visualTargetTracking": {"default": False, "type": "bool"},
        "takeACellfie": {"default": True, "type": "bool"},
        "cellfieHeight": {"default": 30e-6, "type": "float", "suffix": "m"},
        "cellfieStep": {"default": 1e-6, "type": "float", "suffix": "m"},
        "cellfiePipetteClearance": {"default": 100e-6, "type": "float", "suffix": "m"},
        "baselineResistanceTau": {"default": 20, "type": "float", "suffix": "s"},
        "fastDetectionThreshold": {"default": 1e6, "type": "float", "suffix": "Ω"},
        "slowDetectionThreshold": {"default": 0.2e6, "type": "float", "suffix": "Ω"},
        "slowDetectionSteps": {"default": 3, "type": "int"},
        "breakThreshold": {"default": -1e6, "type": "float", "suffix": "Ω"},
        "obstacleDetection": {"default": False, "type": "bool"},
        "obstacleRecoveryTime": {"default": 1, "type": "float", "suffix": "s"},
        "obstacleResistanceThreshold": {"default": 1e6, "type": "float", "suffix": "Ω"},
        "sidestepLateralDistance": {"default": 10e-6, "type": "float", "suffix": "m"},
        "sidestepBackupDistance": {"default": 10e-6, "type": "float", "suffix": "m"},
        "sidestepPassDistance": {"default": 20e-6, "type": "float", "suffix": "m"},
        "pipetteRecalibrateDistance": {"default": 75e-6, "type": "float", "suffix": "m"},
        "pipetteRecalibrationMaxChange": {"default": 15e-6, "type": "float", "suffix": "m"},
        "nextState": {"type": "str", "default": "bath"},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._moveFuture = None
        self._analysis = CellDetectAnalysis(
            self.config["baselineResistanceTau"],
            np.inf,  # not trying to find cells here
            np.inf,  # not trying to find cells here
            999999,  # not trying to find cells here
            self.config["obstacleResistanceThreshold"],
            self.config["breakThreshold"],
        )
        self.direction_unit = self._calc_direction()
        self._wiggleLock = Lock()
        self._sidestepDirection = np.pi / 2
        self._pipetteRecalibrated = False

    def _calc_direction(self):
        # what direction are we moving?
        pip = self.dev.pipetteDevice
        direction = np.array(pip.targetPosition()) - np.array(pip.globalPosition())
        return direction / np.linalg.norm(direction)

    def _onTargetChanged(self, pos):
        super()._onTargetChanged(pos)
        self.direction_unit = self._calc_direction()

    def run(self):
        # move to approach position + auto pipette offset
        self.waitFor(self.dev.pipetteDevice.goApproach("fast"))
        self.dev.clampDevice.autoPipetteOffset()
        self.dev.clampDevice.resetTestPulseHistory()
        self._maybeTakeACellfie()
        if self.config["autoAdvance"]:
            self.monitorTestPulse()
            while True:
                self.checkStop()
                self.processAtLeastOneTestPulse()
                self.adjustPressureForDepth()
                self.maybeRecalibratePipette()
                self.maybeVisuallyTrackTarget()
                if self._analysis.tip_is_broken():
                    self._taskDone(interrupted=True, error="Pipette broken")
                    self.dev.patchRecord()["detectedCell"] = False
                    return "broken"
                if self.obstacleDetected():
                    try:
                        self.avoidObstacle()
                    except TimeoutError:
                        self._taskDone(interrupted=True, error="Fouled by obstacle")
                        return "fouled"
                if self._moveFuture is None:
                    self._moveFuture = self._move()
                if self._moveFuture.isDone():
                    self._moveFuture.wait()  # check for errors
                    self.setState('Move finished; next state')
                    break

        return self.config["nextState"]

    def _maybeTakeACellfie(self):
        config = self.config
        if not config["takeACellfie"] or self._distanceToTarget() <= config["cellfiePipetteClearance"]:
            return
        self.setState("cell detect: taking initial z-stack")
        self.waitFor(self.dev.focusOnTarget("fast"))
        start = self.dev.pipetteDevice.targetPosition()[2] - (config["cellfieHeight"] / 2)
        end = start + config["cellfieHeight"]
        save_in = self.dev.dm.getCurrentDir().getDir("cell detect initial z stack", create=True)
        self.waitFor(
            run_image_sequence(
                self.dev.imagingDevice(),
                z_stack=(start, end, config["cellfieStep"]),
                storage_dir=save_in,
            )
        )

    def maybeRecalibratePipette(self):
        if self._pipetteRecalibrated:
            return
        if self._distanceToTarget() < self.config["pipetteRecalibrateDistance"]:
            if self._moveFuture is not None:
                # should restart on next main loop
                self._moveFuture.stop(wait=True)

            pip = self.dev.pipetteDevice
            imgr = self.dev.imagingDevice()
            manager = getManager()
            with manager.reserveDevices(
                [pip, imgr, imgr.scopeDev.positionDevice(), imgr.scopeDev.focusDevice()], timeout=30.0
            ):
                self.sleep(1.0)
                initial_pos = pos = np.array(pip.globalPosition())
                self.waitFor(self.dev.imagingDevice().moveCenterToGlobal(pos, "fast"))
                self.setState(f"First recalibrate position (starting at {pos})")
                self.sleep(1.0)
                pos = pip.tracker.findTipInFrame()
                self.waitFor(self.dev.imagingDevice().moveCenterToGlobal(pos, "fast"))
                self.setState(f"Second recalibrate position (found tip at {pos})")
                self.sleep(1.0)
                pos = pip.tracker.findTipInFrame()
                dist = np.linalg.norm(initial_pos - pos)
                if dist < self.config["pipetteRecalibrationMaxChange"]:
                    pip.resetGlobalPosition(pos)
                    self.setState(f"Recalibrate finished (found tip again at {pos})")
                else:
                    self.setState(f"cancel pipette position update; prediction is too far away ({dist*1e6}um)")

            self._pipetteRecalibrated = True

    @future_wrap
    def _move(self, _future):
        config = self.config
        if self.aboveSurface():
            self.setState("move to surface")
            self._waitForMoveWhileTargetChanges(
                self.surfaceIntersectionPosition, config['aboveSurfaceSpeed'], True, _future)
        self.setState(f'move to endpoint: {self.endpoint()}')
        self._waitForMoveWhileTargetChanges(
            position_fn=self.endpoint,
            speed=config['belowSurfaceSpeed'],
            continuous=config["advanceContinuous"],
            future=_future,
            interval=config['advanceStepInterval'],
            step=config['advanceStepDistance'],
        )

    def endpoint(self):
        """Return the last position along the pipette search path to be traveled at full speed."""
        pip = self.dev.pipetteDevice
        target = np.array(pip.targetPosition())
        return target - (self.direction_unit * self.config["minDetectionDistance"])

    def obstacleDetected(self):
        return (
            self.config["obstacleDetection"]
            and not self.closeEnoughToTargetToDetectCell()
            and self._analysis.obstacle_detected()
        )

    def sidestepDirection(self, vector):
        """
        Create a vector orthogonal to the input vector, oriented π/2 radians more widdershins than last invocation.

        Parameters:
        vector : ndarray
            the direction vector to sidestep from

        Return : ndarray
            a unit vector orthogonal to the input vector
        """
        self._sidestepDirection += np.pi / 2
        unit_vector = vector / np.linalg.norm(vector)

        # Create an arbitrary orthogonal vector
        min_idx = np.argmin(np.abs(unit_vector))
        basis = np.zeros(3)
        basis[min_idx] = 1
        ortho_vec = np.cross(unit_vector, basis)
        ortho_vec = ortho_vec / np.linalg.norm(ortho_vec)

        ortho_vec2 = np.cross(unit_vector, ortho_vec)

        # Apply the rotation by angle in the plane of ortho_vec and ortho_vec2
        return ortho_vec * np.cos(self._sidestepDirection) + ortho_vec2 * np.sin(self._sidestepDirection)

    def avoidObstacle(self, already_retracted=False):
        self.setState("avoiding obstacle" + (" (recursively)" if already_retracted else ""))
        if self._moveFuture is not None:
            self._moveFuture.stop("Obstacle detected")
            self.waitForStop()

        pip = self.dev.pipetteDevice
        speed = self.config["belowSurfaceSpeed"]

        init_pos = np.array(pip.globalPosition())
        direction = self.direction_unit
        if already_retracted:
            retract_pos = init_pos
        else:
            retract_pos = init_pos - self.config["sidestepBackupDistance"] * direction
            self.waitFor(pip._moveToGlobal(retract_pos, speed=speed))

        start_time = ptime.time()
        while self._analysis.obstacle_detected():
            self.processAtLeastOneTestPulse()
            if ptime.time() - start_time > self.config["obstacleRecoveryTime"]:
                raise TimeoutError("Pipette fouled by obstacle")

        # pick a sidestep point orthogonal to the pipette direction on the xy plane
        sidestep = self.config["sidestepLateralDistance"] * self.sidestepDirection(direction)
        sidestep_pos = retract_pos + sidestep
        self.waitFor(pip._moveToGlobal(sidestep_pos, speed=speed))

        go_past_pos = sidestep_pos + self.config["sidestepPassDistance"] * direction
        move = pip._moveToGlobal(go_past_pos, speed=speed)
        while not move.isDone():
            self.processAtLeastOneTestPulse()
            if self._analysis.obstacle_detected():
                move.stop("Obstacle detected while sidestepping")
                self.waitFor(pip._moveToGlobal(retract_pos, speed=speed))
                return self.avoidObstacle(already_retracted=True)
            self.checkStop()
        self.waitFor(move)
        pos = np.array(pip.globalPosition())
        self.waitFor(pip._moveToGlobal(pos - sidestep, speed=speed))

    def _cleanup(self):
        if self._moveFuture is not None and not self._moveFuture.isDone():
            try:
                self._moveFuture.stop("State finished", wait=True)
            except Exception:
                printExc("Error stopping pipette advance during cleanup")

        return super()._cleanup()
