from __future__ import annotations

import numpy as np
from gentletask import check_stop

from acq4.util.debug import log_and_ignore_exception
from acq4.util.task import sleep, Stopped
from pyqtgraph.units import µm, MΩ
from ._base import PatchPipetteState
from .cell_detect import CellDetectAnalysis


class ContactCellState(PatchPipetteState):
    """Handles approaching and contacting a cell with visual tracking and resistance monitoring.

    This state:
    1. Calls newCell() if needed
    2. Starts monitoring test pulses
    3. Enables visual target tracking
    4. Lifts the tip clear of the sample surface, crosses to the target's x,y at that height,
       and comes down to 7 µm above the target
    5. In a loop:
       - Moves the pipette to the x,y coordinates of the tracked target, stepping down 1 µm in z
       - Checks for cell membrane contact via resistance increase
       - Once contact is detected, continues until 3 µm below the contact depth
       - If 15 µm traveled without detection, proceeds to seal anyway

    Parameters
    ----------
    stepSize : float
        Distance (m) to step downward per iteration (default 1 µm)
    stepInterval : float
        Time (s) to wait between steps (default 2 s)
    initialApproachHeight : float
        Height (m) above target to start approach (default 7 µm)
    findPipette : bool
        if True, visually update the pipette tip location after moving to approach position and before descending towards cell
    depthPastContact : float
        Distance (m) to travel past initial contact before transitioning to seal (default 3 µm)
    maxTravelWithoutContact : float
        Maximum distance (m) to travel without detecting contact before giving up (default 15 µm)
    moveSpeed : float
        Speed (m/s) for pipette movements (default 5 µm/s)
    baselineResistanceTau : float
        Time constant (s) for rolling average of pipette resistance (default 20 s)
    fastDetectionThreshold : float
        Threshold for fast change in pipette resistance (Ohm) to trigger cell detection (default 1 MOhm)
    slowDetectionThreshold : float
        Threshold for slow change in pipette resistance (Ohm) to trigger cell detection (default 200 kOhm)
    slowDetectionSteps : int
        Number of test pulses to integrate for slow change detection (default 3)
    breakThreshold : float
        Threshold for change in resistance (Ohm) to detect broken pipette (default -1 MOhm)
    pipetteRecalibrationMaxChange : float
        Maximum allowed change in pipette position during recalibration before rejecting update (default 5 µm)
    visualTargetTracking : bool
        Whether to visually track the target cell during descent (default True)
    overshootDistance : float
        Distance (m) the cell is expected to be pushed along the pipette axis as the tip
        reaches it. The whole descent is aimed at target + overshootDistance * axis, so it
        carries a lateral component as well as a vertical one. Only meaningful with
        visualTargetTracking off, since the tracker already follows the displaced cell
        (default 0)
    minDetectionDistance : float
        Minimum distance (m) from target before cell detection is considered; negative disables
        the limit (default -1)
    nextState : str
        Name of the state to transition to once contact is established (default "seal")
    """

    stateName = 'contact cell'
    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'stepSize': {'default': 1 * µm, 'type': 'float', 'suffix': 'm'},
        'stepInterval': {'default': 2.0, 'type': 'float', 'suffix': 's'},
        'initialApproachHeight': {'default': 7 * µm, 'type': 'float', 'suffix': 'm'},
        'findPipette': {'default': False, 'type': 'bool'},
        'depthPastContact': {'default': 3 * µm, 'type': 'float', 'suffix': 'm'},
        'maxTravelWithoutContact': {'default': 15 * µm, 'type': 'float', 'suffix': 'm'},
        'moveSpeed': {'default': 5 * µm, 'type': 'float', 'suffix': 'm/s'},
        'baselineResistanceTau': {'default': 20, 'type': 'float', 'suffix': 's'},
        'fastDetectionThreshold': {'default': 1*MΩ, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionThreshold': {'default': 0.2*MΩ, 'type': 'float', 'suffix': 'Ω'},
        'slowDetectionSteps': {'default': 3, 'type': 'int'},
        'breakThreshold': {'default': -1*MΩ, 'type': 'float', 'suffix': 'Ω'},
        "nextState": {"type": "str", "default": "seal"},
        "pipetteRecalibrationMaxChange": {"type": "float", "default": 5 * µm, "suffix": "m"},
        "visualTargetTracking": {"default": True, "type": "bool"},
        "overshootDistance": {'default': 0, 'type': 'float', 'suffix': 'm'},
        "minDetectionDistance": {'default': -1, 'type': 'float', 'suffix': 'm'},
    }

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._analysis = CellDetectAnalysis(
            baseline_tau=self.config['baselineResistanceTau'],
            cell_threshold_fast=self.config['fastDetectionThreshold'],
            cell_threshold_slow=self.config['slowDetectionThreshold'],
            slow_detection_steps=self.config['slowDetectionSteps'],
            break_threshold=self.config['breakThreshold'],
        )
        self._moveFuture = None
        self._contactDepth = None
        self._startZ = None

    def run(self):
        config = self.config
        pip = self.dev.pipetteDevice
        # Track how far setup got, so a stop/exception before the main loop is explained.
        # This state has been observed being stopped within milliseconds of entry (before any
        # setState fired), which looked like an immediate, unexplained bounce to the fallback.
        phase = "starting"

        try:
            self.setState("contact cell: initializing")

            # 1. Create new cell if needed
            if self.dev.cell is None:
                phase = "creating new cell"
                self.dev.newCell()

            # 2. Start monitoring test pulses
            phase = "starting test pulse monitoring"
            self.monitorTestPulse()

            # 3. Enable visual target tracking (only when requested and a cell exists).
            #    newCell() silently leaves cell=None if acq4_automation is unavailable, so
            #    guard explicitly instead of crashing into the fallback state with no message.
            if config['visualTargetTracking']:
                if self.dev.cell is None:
                    self.setState(
                        "visual target tracking unavailable (no cell assigned; is acq4_automation "
                        "installed?); continuing descent without tracking"
                    )
                else:
                    phase = "enabling visual target tracking"
                    self.startVisualTargetTracking(allow_refresh_reference=True)

            if config['visualTargetTracking'] and config['overshootDistance'] != 0:
                self.setState(
                    "warning: overshootDistance is double-counted while visual target "
                    "tracking is on; the tracker already follows the displaced cell"
                )

            # 4. Clear the sample, then come down to initial approach height above the target
            phase = "moving to initial descent position"
            target = np.array(pip.targetPosition())
            # The cell is expected to be pushed this far along the pipette axis as the tip
            # reaches it, so the descent is aimed at the displaced position: axial, not vertical.
            overshoot = config['overshootDistance'] * pip.globalDirection()
            descent_start = target + overshoot
            descent_start[2] += config['initialApproachHeight']
            self.setState("moving to initial descent position")
            self._moveToDescentStart(descent_start)

            if config['findPipette']:
                self.findPipetteTip(zstack=True)

            if not config['visualTargetTracking']:
                self.dev.focusOnTarget("fast").wait()

            # Sampled where the tip actually is, so it already carries the overshoot's z
            # component; the descent loop adds only the lateral part of the overshoot.
            self._startZ = pip.globalPosition()[2]
            iterations = 0
            # The descent is quantised to stepSize, so a depth that lands within float error of
            # the configured one is the depth that was asked for. Without this, 3 µm of travel
            # arriving as 2.9999999999999984e-06 buys a whole extra step of glass in the cell.
            # The same accumulated error decides maxTravelWithoutContact, where the extra step
            # is a micron of blind descent past the depth the operator set.
            depth_tolerance = config['stepSize'] * 1e-6

            # 5. Main descent loop
            phase = "descending toward cell"
            self.setState("descending toward cell")
            while True:
                check_stop()

                # Process test pulses and check for broken tip
                self.processAtLeastOneTestPulse()
                if self._analysis.tip_is_broken():
                    self.setState(f"{self.stateName} failed: pipette break detected")
                    self.dev.patchRecord()['detectedCell'] = False
                    return {"state": 'broken', "error": "Pipette break detected"}

                # Check if cell membrane detected
                if self._cellDetected():
                    if self._contactDepth is None:
                        current_z = pip.globalPosition()[2]
                        self._contactDepth = current_z
                        self.setState("cell contact detected, continuing descent")
                        self.dev.patchRecord()['detectedCell'] = True
                        self.dev.patchRecord()['contactDepth'] = current_z

                # Check if we should transition to seal
                if self._contactDepth is not None:
                    current_z = pip.globalPosition()[2]
                    depth_past_contact = self._contactDepth - current_z
                    if depth_past_contact >= config['depthPastContact'] - depth_tolerance:
                        self.setState(f"reached target depth past contact; advancing to {config['nextState']}")
                        return {"state": config['nextState']}

                # Check if we've traveled too far without contact
                current_z = pip.globalPosition()[2]
                total_descent = self._startZ - current_z
                if total_descent >= config['maxTravelWithoutContact'] - depth_tolerance:
                    self.setState(
                        f"{self.stateName} failed: traveled "
                        f"{total_descent * 1e6:0.1f} µm without contact; "
                        f"falling back to {config['fallbackState']}"
                    )
                    self.dev.patchRecord()['detectedCell'] = False
                    return {"state": config['fallbackState']}

                # Get target xy from visual tracking (if available), keep stepping down in z
                target_xy = np.asarray(pip.targetPosition()[:2]) + overshoot[:2]
                iterations += 1
                next_pos = np.array([
                    target_xy[0],
                    target_xy[1],
                    self._startZ - iterations * config['stepSize'],
                ])
                self._moveTip(next_pos, 'contact cell descent step')

                # Wait between iterations
                duration = config['stepInterval']
                sleep(duration)
        except Stopped as exc:
            # Cooperative stop (state manager / device deactivated); let it propagate so the
            # framework handles it normally without treating it as a failure. Log the phase and
            # reason first: this state has been seen stopping almost immediately after entry,
            # which without this leaves no trace of where/why the descent was aborted.
            self.logger.info(f"contact cell stopped during phase {phase!r} (reason: {exc!r})")
            raise
        except Exception as exc:
            # Any other error (e.g. failed move, tracker init, pipette recalibration) would
            # otherwise fall through to the default fallback state with no explanation. Emit a
            # clear message and route to the fallback state explicitly.
            self.logger.exception(f"Unexpected error in contact cell state during phase {phase!r}")
            self.setState(
                f"{self.stateName} failed during {phase}: {type(exc).__name__}: {exc}; "
                f"falling back to {config['fallbackState']}"
            )
            with log_and_ignore_exception(Exception, "Error recording failed cell detection"):
                self.dev.patchRecord()['detectedCell'] = False
            return {"state": config['fallbackState']}

    def _moveTip(self, pos, name):
        """Command a move to *pos* and wait for it, tracking the future for cleanup."""
        pip = self.dev.pipetteDevice
        self._moveFuture = pip.moveToGlobalNoPlanning(pos, speed=self.config['moveSpeed'], name=name)
        self._moveFuture.wait()
        self._moveFuture = None

    def _moveToDescentStart(self, descent_start):
        """Bring the tip to *descent_start* without dragging it sideways through the slice.

        *descent_start* is initialApproachHeight above the target, which for any target in
        tissue is still below the surface, so it is the surface depth that decides how high the
        tip has to be before it may cross to the target's x,y. The tip rises to that height
        (never falls to it), crosses, and only then comes down.
        """
        pip = self.dev.pipetteDevice
        start = np.asarray(pip.globalPosition(), dtype=float)
        surface = pip.scopeDevice().getSurfaceDepth()
        if surface is None:
            raise ValueError("Cannot clear the sample before traversing; surface depth is not defined.")
        cross_z = max(descent_start[2], surface, start[2])

        if cross_z > start[2]:
            lift = start.copy()
            lift[2] = cross_z
            self._moveTip(lift, 'lift to tissue clearance height')
        if cross_z > descent_start[2]:
            cross = descent_start.copy()
            cross[2] = cross_z
            self._moveTip(cross, 'traverse above the slice to the descent start')
        self._moveTip(descent_start, 'move to initial approach position')

    def processAtLeastOneTestPulse(self):
        tps = super().processAtLeastOneTestPulse()
        self._analysis.process_test_pulses(tps)
        return tps

    def _cellDetected(self) -> bool:
        """Check if cell membrane has been detected via resistance change."""
        return self._analysis.cell_detected_fast() or self._analysis.cell_detected_slow()

    # def _enableVisualTracking(self):
    #     """Enable visual tracking of the cell."""
    #     cell = self.dev.cell
    #     if cell is None:
    #         return
    #     if not cell.isInitialized:
    #         cell.initializeTracker(self.dev.pipetteDevice.imagingDevice()).wait()
    #     self._cell = cell
    #     cell.enableTracking(True)

    # def _disableVisualTracking(self):
    #     """Disable visual tracking of the cell."""
    #     if self._cell is not None:
    #         self._cell.enableTracking(False)
    #         self._cell = None

    def _cleanup(self):
        if self._moveFuture is not None and not self._moveFuture.is_done:
            with log_and_ignore_exception(Exception, "Error stopping move during cleanup"):
                self._moveFuture.stop()
        # with log_and_ignore_exception(Exception, "Error disabling visual tracking"):
        #     self._disableVisualTracking()
        super()._cleanup()
        with log_and_ignore_exception(Exception, "Error focusing on target during cleanup"):
            self.dev.focusOnTarget("fast").wait()

    def findPipetteTip(self, zstack=True):
        pip = self.dev.pipetteDevice
        self.setState(f"Check pipette tip..")
        try:
            if zstack:
                self.stopVisualTargetTracking('pause tracking for pipette recalibration')
                try:
                    pip.findTipInStack(maxOffsetDistance=5e-6)
                finally:
                    self.startVisualTargetTracking()
            else:
                pip.iterativelyFindTip(
                    max_allowed_offset=self.config["pipetteRecalibrationMaxChange"],
                    go_to_tip_first=True,
                    focus_above=2e-6,
                )
        except Exception as e:
            self.logger.exception(e)
            self.setState(f"failed pipette position update: {e}")
