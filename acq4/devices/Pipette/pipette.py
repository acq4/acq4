from __future__ import annotations

import contextlib
import json
import os
import weakref
from typing import List

import numpy as np

import pyqtgraph as pg
from acq4 import getManager
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage, MovePathFuture
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt, ptime
from acq4.util.future import future_wrap
from acq4.util.target import Target
from pyqtgraph import Point, siFormat
from .planners import PipettePathGenerator
from .planners import defaultMotionPlanners
from .tracker import ResnetPipetteTracker
from ..Camera import Camera
from ..RecordingChamber import RecordingChamber
from ...util.PromptUser import prompt
from ...util.geometry import Plane
from ...util.imaging.sequencer import run_image_sequence

CamModTemplate = Qt.importTemplate('.cameraModTemplate')


class Pipette(Device, OptomechDevice):
    """Represents a pipette or electrode attached to a motorized manipulator.

    This device provides a camera module interface for driving a motorized electrode holder:

    * Visually direct pipette tip via camera module
    * Automatically align pipette tip for diagonal approach to cells
    * Automatically calibrate pipette tip position (via Tracker)

    This device must be configured with a Stage as its parent.

    The local coordinate system of the device is configured such that the X axis points in the direction of the pipette
    tip, the Z axis points upward (same as global +Z), and the Y axis is the vector perpendicular to both X and Z.

    Configuration options:

    * **pitch** (float or 'auto', required): The angle of the pipette (in degrees) relative to the horizontal plane.
      Positive values point downward. This option must be specified in the configuration.
      If the value 'auto' is given, then the pitch is derived from the parent manipulator's X axis
      (or other specified by parentAutoAxis) pitch.
      
    * **yaw** (float or 'auto', required): The angle of the pipette (in degrees) relative to the global +X axis (points to the operator's right
      when facing the microscope).
      Positive values are clockwise from global +X. This option must be specified in the configuration.
      If the value 'auto' is given, then the yaw is derived from the parent manipulator's X axis
      (or other specified by parentAutoAxis) yaw.
      
    * **parentAutoAxis** (str, optional): One of '+x' (default), '-x', '+y', '-y', '+z', or '-z' indicating the axis and direction in the
      parent manipulator's coordinate system that points along the pipette and toward the tip. This axis
      is used by the *pitch* and *yaw* options when they are set to 'auto'. If the pipette is not parallel
      to one of these axes, then a numerical value must be provided for the pitch and/or yaw.
      
    * **searchHeight** (float, optional): The distance to focus above the sample surface when searching for pipette tips. This
      should be about 1-2mm, enough to avoid collisions between the pipette tip and the sample during search.
      Default is 2 * mm.
      
    * **searchTipHeight** (float, optional): The distance above the sample surface to bring the (putative) pipette tip position
      when searching for new pipette tips. For low working-distance objectives, this should be about 0.5 mm less
      than *searchHeight* to avoid collisions between the tip and the objective during search.
      Default is 1.5 * mm.
      
    * **approachHeight** (float, optional): The distance to bring the pipette tip above the sample surface when beginning
      a diagonal approach. Default is 100 * um.
      
    * **idleHeight** (float, optional): The distance to bring the pipette tip above the sample surface when in idle position.
      Default is 1 * mm.
      
    * **idleDistance** (float, optional): The x/y distance from the global origin from which the pipette top should be placed
      in idle mode. Default is 7 * mm.
      
    * **recordingChambers** (list, optional): List of names of RecordingChamber devices that this Pipette is meant to work with.
    
    * **reasonableTipOffsetDistance** (float, optional): When updating the tip offset, this is the maximum distance (in meters)
        from the original tip offset that is considered reasonable. If the tip offset is outside this distance, 
        the user will be prompted to confirm the new offset. Default is 30 * um.

    Standard OptomechDevice configuration options (see OptomechDevice base class):

    * **parentDevice** (str, required): Name of parent Stage device (manipulator)

    * **transform** (dict, optional): Spatial transform relative to parent device

    Example configuration::

        PatchPipette1:
            driver: 'Pipette'
            parentDevice: 'Manipulator1'
            pitch: 15.0
            yaw: 45.0
            searchHeight: 2 * mm
            approachHeight: 100 * um
            idleHeight: 1 * mm
            recordingChambers: ['Chamber1']
    """

    sigTargetChanged = Qt.Signal(object, object)
    sigCalibrationChanged = Qt.Signal(object)

    # move start/finish are used for recording coarse movement information;
    # they are not emitted for every transform change.
    sigMoveStarted = Qt.Signal(object, object)  # self, pos
    sigMoveFinished = Qt.Signal(object, object)  # self, pos
    sigMoveRequested = Qt.Signal(object, object, object, object)  # self, pos, speed, opts

    # May add items here to implement custom motion planning for all pipettes
    defaultMotionPlanners = defaultMotionPlanners()
    pathGeneratorClass = PipettePathGenerator

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
        self.config = config
        self.moving = False
        self._scopeDev = None
        self._imagingDev = None
        self._boundaries = None
        self._opts = {
            'searchHeight': config.get('searchHeight', 2e-3),
            'searchTipHeight': config.get('searchTipHeight', 1.5e-3),
            'approachHeight': config.get('approachHeight', 100e-6),
            'cleanApproachHeight': config.get('cleanApproachHeight', 1500e-6),
            'idleHeight': config.get('idleHeight', 1e-3),
            'idleDistance': config.get('idleDistance', 7e-3),
            'showCameraModuleUI': config.get('showCameraModuleUI', False),
        }
        parent = self.parentDevice()
        if not isinstance(parent, Stage):
            raise Exception(
                f"Pipette device requires some type of translation stage as its parentDevice (got {parent}).")

        parent.sigOrientationChanged.connect(self.clearSavedOffsets)
        # may add items here to implement per-pipette custom motion planning
        self.motionPlanners = {}
        self.currentMotionPlanner = None
        self.keepOnStepping = True
        self.pathGenerator = self.pathGeneratorClass(self)

        self._camInterfaces = weakref.WeakKeyDictionary()

        self.target = None

        cal = self.readConfigFile('calibration')
        self.offset = np.array(cal.get('offset', [0, 0, 0]))
        # kept for backward compatibility
        self._calibratedPitch = cal.get('pitch', None)
        self._calibratedYaw = cal.get('yaw', cal.get('angle', None))  # backward support for old 'angle' config key

        self._globalDirection = None
        self._localDirection = None

        # timer used to emit sigMoveFinished when no motion is detected for a certain period
        self.moveTimer = Qt.QTimer()
        self.moveTimer.timeout.connect(self.positionChangeFinished)
        self.sigGlobalTransformChanged.connect(self.positionChanged)

        # If parent orientation changes (probably due to being recalibrated), update pitch/yaw angles if needed.
        parent.sigOrientationChanged.connect(self._directionChanged)

        self._updateTransform()

        self.tracker = ResnetPipetteTracker(self)
        deviceManager.declareInterface(name, ['pipette'], self)

        target = self.readConfigFile('target').get('targetGlobalPosition', None)
        if target is not None:
            self.setTarget(target)

        deviceManager.sigAbortAll.connect(self.stop)

    def getGeometry(self):
        if isinstance(self.config.get("geometry"), dict):
            defaults = {'color': (0, 1, 0.2, 1)}
            defaults.update(self.config["geometry"])
            self.config["geometry"] = defaults
        return super().getGeometry()

    def getBoundaries(self) -> List[Plane]:
        if self._boundaries is None:
            self._boundaries = []
            for plane in self.parentDevice().getBoundaries():
                mapped_pt = self._solveMyGlobalPosition(plane.point)
                mapped_vec = self._solveMyGlobalPosition(plane.point + plane.normal) - mapped_pt
                new_name = self.name() + " " + plane.name.partition(" ")[2]
                self._boundaries.append(Plane(mapped_vec, mapped_pt, new_name))

        return self._boundaries

    def moveTo(self, position: str, speed, raiseErrors=False, **kwds):
        """Move the pipette tip to a named position, with safe motion planning.

        If *raiseErrors* is True, then an exception will be raised in a background
        thread if the move fails.
        """
        # Select a motion planner based on the target position
        plannerClass = self.motionPlanners.get(position, self.defaultMotionPlanners.get(position, None))
        if plannerClass is None:
            savedPos = self.loadPosition(position)
            if savedPos is not None:
                plannerClass = self.motionPlanners.get('saved', self.defaultMotionPlanners.get('saved', None))

        if plannerClass is None:
            raise ValueError(f"Unknown pipette move position {position!r}")

        if self.currentMotionPlanner is not None:
            self.currentMotionPlanner.stop()

        self.currentMotionPlanner = plannerClass(self, position, speed, **kwds)
        future = self.currentMotionPlanner.move()
        if raiseErrors is not False:
            future.raiseErrors(message=f"Move to {position} position failed ({{error}}); requested from:\n{{stack}}")

        return future

    def savePosition(self, name, pos=None):
        """Store a position in global coordinates for later use.

        If no position is provided, then the current position of the pipette tip is used.
        """
        if pos is None:
            pos = self.globalPosition()
        manip_pos = self._solveGlobalStagePosition(pos)
        manip: Stage = self.parentDevice()
        manip.checkLimits(manip.mapGlobalToDevicePosition(manip_pos))

        cache = self.readConfigFile('stored_positions')
        cache[name] = list(pos)
        self.writeConfigFile(cache, 'stored_positions')
        self.checkRangeOfMotion(pos)

    def loadPosition(self, name, default=None):
        """Return a previously saved position.
        """
        cache = self.readConfigFile('stored_positions')
        return cache.get(name, default)

    def checkRangeOfMotion(self, pos, tolerance=500e-6):
        """Warn user if the position (in global coordinates) is within 500µm of the manipulator's range of motion."""
        manipulator: Stage = self.parentDevice()
        manipulator.checkRangeOfMotion(self._solveGlobalStagePosition(pos), tolerance)

    def scopeDevice(self):
        if self._scopeDev is None:
            imdev = self.imagingDevice()
            self._scopeDev = imdev.scopeDev
        return self._scopeDev

    def imagingDevice(self) -> Camera:
        if self._imagingDev is None:
            man = getManager()
            name = self.config.get('imagingDevice', None)
            if name is None:
                cams = man.listInterfaces('camera')
                if len(cams) == 1:
                    name = cams[0]
                else:
                    raise Exception(
                        "Pipette requires either a single imaging device available (found %d) or 'imagingDevice' specified in its configuration." % len(
                            cams))
            self._imagingDev = man.getDevice(name)
        return self._imagingDev

    def quit(self):
        pass

    def stop(self):
        self.keepOnStepping = False  # thread safety? if a user starts a new stepwise movement simultaneous with stopping, they deserve to have to stop a second or even third time.
        cmp = self.currentMotionPlanner
        if cmp is not None:
            cmp.stop()

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PipetteDeviceGui(self, win)

    def cameraModuleInterface(self, mod):
        iface = PipetteCamModInterface(self, mod, showUi=self._opts['showCameraModuleUI'])
        self._camInterfaces[iface] = None
        return iface

    def tipOffsetIsReasonable(self, pos) -> bool:
        dist = np.linalg.norm(np.array(self.mapToGlobal((0, 0, 0))) - pos)
        return dist < self.config.get("reasonableTipOffsetDistance", 30e-6)

    def newPipetteTipOffsetIsReasonable(self, pos) -> bool:
        cal = self.readConfigFile('calibration')
        if 'offset history' in cal and len(cal['offset history']) > 10:
            avg = np.mean(cal['offset history'], axis=0)
            sigma = np.std(np.linalg.norm(np.array(cal['offset history']) - avg, axis=1))
            if np.linalg.norm(np.array(pos) - avg) > 3 * sigma:
                return False
        return True

    @future_wrap
    def setTipOffsetIfAcceptable(self, pos, _future=None):
        if self.tipOffsetIsReasonable(pos):
            self.resetGlobalPosition(pos)
        else:
            dist = np.linalg.norm(np.array(self.mapToGlobal((0, 0, 0))) - pos)
            dist = siFormat(dist, suffix='m', precision=3)
            button_text = _future.waitFor(prompt(
                title="Pipette displacement detected",
                text=f"The tip offset for {self.name()} is {dist} off from its initial value.",
                extra_text="Do you want to use it, discard it or override all historic offsets?",
                choices=["Use", "Discard", "Override"],
            ), timeout=None).getResult()
            if button_text == "Use":
                self.resetGlobalPosition(pos)
            elif button_text == "Discard":
                return False
            elif button_text == "Override":
                self.overrideTipOffsetHistory(pos)
            else:
                raise AssertionError("Unknown button clicked")
        return True

    @future_wrap
    def setNewPipetteTipOffsetIfAcceptable(self, pos, _future=None):
        """Returns whether the tip position was saved. Otherwise, the user requested a re-do."""
        if self.newPipetteTipOffsetIsReasonable(pos):
            self.recordTipOffsetInHistory(pos)
        else:
            button_text = _future.waitFor(prompt(
                title="Initial tip offset outlier",
                text=f"The tip offset for {self.name()} is outside of its normal range.",
                extra_text="Do you want to include this outlier, discard the value, override all historic "
                           "offsets, or only use this as a temporary offset?",
                choices=["Include", "Discard", "Override", "Temporary"],
            ), timeout=None).getResult()
            if button_text == "Include":
                self.recordTipOffsetInHistory(pos)
            elif button_text == "Discard":
                return False
            elif button_text == "Override":
                self.overrideTipOffsetHistory(pos)
            elif button_text == "Temporary":
                self.setTipOffset(pos)
            else:
                raise AssertionError("Unknown button clicked")
        return True

    def recordTipOffsetInHistory(self, pos):
        self.resetGlobalPosition(pos)
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(self.offset)
        cal.setdefault('offset history', []).append(cal['offset'])
        cal['offset history'] = cal['offset history'][-20:]
        self.writeConfigFile(cal, 'calibration')

    def overrideTipOffsetHistory(self, pos):
        self.resetGlobalPosition(pos)
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(self.offset)
        cal['offset history'] = [cal['offset']]
        self.writeConfigFile(cal, 'calibration')

    def clearSavedOffsets(self, parent):
        """Clear the saved offsets if the parent manipulator's axes are re-calibrated."""
        cal = self.readConfigFile('calibration')
        if 'offset history' in cal:
            del cal['offset history']
            self.writeConfigFile(cal, 'calibration')

    def setTipOffset(self, pos):
        """Given a global position, set the offset such that the pipette tip is located at that position."""
        self.resetGlobalPosition(pos)
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(self.offset)
        self.writeConfigFile(cal, 'calibration')

    def averageHistoricOffset(self):
        cal = self.readConfigFile('calibration')
        if 'offset history' in cal and len(cal['offset history']) > 0:
            return np.mean(cal['offset history'], axis=0)
        else:
            return self.offset

    @future_wrap
    def saveManualCalibration(self, _future):
        path = os.path.join(self.configPath(), "manual-calibrations")
        path = self.dm.configFileName(path)
        path = self.dm.dirHandle(path, create=True)

        cam: Camera = self.imagingDevice()
        depth = cam.getFocusDepth()
        is_below_surface = depth <= self.scopeDevice().getSurfaceDepth()
        scan_dist = np.random.randint(2, 40 if is_below_surface else 100) * 1e-6
        step = scan_dist / 2
        try:
            seq_future = run_image_sequence(cam, z_stack=(depth - scan_dist, depth + scan_dist, step), storage_dir=path)
            _future.waitFor(seq_future)
        finally:
            _future.waitFor(cam.setFocusDepth(depth))
        fh = seq_future.imagesSavedIn
        info = {
            **fh.info(),
            "tip position": self.globalPosition(),
        }
        fh.setInfo(info)

    def resetGlobalPosition(self, pos):
        """Set the device transform such that the pipette tip is located at the global position *pos*.

        This method is for recalibration; it does not physically move the device.
        """
        lpos = np.array(self.mapFromGlobal(pos))
        self.setOffset(self.offset + lpos)

    def setOffset(self, offset):
        self.offset = np.array(offset)
        self._updateTransform()
        self.sigCalibrationChanged.emit(self)

    def _updateTransform(self):
        # matrix mapping from local to parent
        x = self.globalDirection()
        x[2] = 0
        x = x / np.linalg.norm(x)
        z = np.array([0, 0, 1])
        y = np.cross(x, z)
        y = y / np.linalg.norm(y)
        m = np.array([
            [x[0], y[0], z[0], 0],
            [x[1], y[1], z[1], 0],
            [x[2], y[2], z[2], 0],
            [0, 0, 0, 1],
        ])
        tr = pg.Transform3D(m)
        tr.translate(*self.offset)
        self.setDeviceTransform(tr)

    def _directionChanged(self):
        """Orientation has changed
        """
        self._globalDirection = None
        self._localDirection = None
        self._updateTransform()

    def saveCalibration(self):
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(self.offset)

        # kept for backward compatibility
        if self._calibratedPitch is not None:
            cal['pitch'] = self._calibratedPitch
        if self._calibratedYaw is not None:
            cal['yaw'] = self._calibratedYaw

        self.writeConfigFile(cal, 'calibration')

    def yawAngle(self):
        """Return the yaw (azimuthal angle) of the electrode around the Z-axis in degrees.

        Value is returned in degrees such that an angle of 0 indicate the tip points along the positive x axis,
        and 90 points along the positive y axis.
        """
        if 'yaw' not in self.config:
            # for backward compatibility
            if self._calibratedYaw is not None:
                return self._calibratedYaw
            raise ValueError(f"Yaw angle is not configured for {self.name()}")
        if self.config['yaw'] == 'auto':
            return self._manipulatorOrientation()['yaw']
        else:
            return self.config['yaw']

    def pitchAngle(self):
        """Return the pitch of the electrode in degrees (angle relative to horizontal plane).

        For positive angles, the pipette tip points downward, toward -Z. 
        """
        if 'pitch' not in self.config:
            # for backward compatibility
            if self._calibratedPitch is not None:
                return self._calibratedPitch
            raise ValueError(f"Pitch angle is not configured for {self.name()}")
        if self.config['pitch'] == 'auto':
            return self._manipulatorOrientation()['pitch']
        else:
            return self.config['pitch']

    def _manipulatorOrientation(self) -> dict:
        axis = self.config.get('parentAutoAxis', '+x')
        return self.parentDevice().calculatedAxisOrientation(axis)

    def yawRadians(self):
        return self.yawAngle() * np.pi / 180.

    def pitchRadians(self):
        return self.pitchAngle() * np.pi / 180.

    def goHome(self, speed='fast', **kwds):
        """Extract pipette tip diagonally, then move to home position.
        """
        return self.moveTo('home', speed=speed, **kwds)

    def goSearch(self, speed='fast', distance=0, **kwds):
        return self.moveTo('search', speed=speed, distance=distance, **kwds)

    def goApproach(self, speed, **kwds):
        """Move the electrode tip such that it is 100um above the sample surface with its
        axis aligned to the target. 
        """
        return self.moveTo('approach', speed=speed, **kwds)

    def goIdle(self, speed='fast', **kwds):
        return self.moveTo('idle', speed=speed, **kwds)

    def goTarget(self, speed, **kwds):
        return self.moveTo('target', speed=speed, **kwds)

    def goAboveTarget(self, speed, **kwds):
        return self.moveTo('aboveTarget', speed=speed, **kwds)

    def _movePath(self, path) -> MovePathFuture:
        """
        move along a path defined in global coordinates.
        Format is [(pos, speed, linear, explanation), ...]
        returns the movefuture of the last move.
        WARNING: This method does _not_ implement any motion planning.
        """

        self.sigMoveRequested.emit(self, path[-1][0], None, {'path': path})
        stagePath = []
        for pos, speed, linear, explanation in path:
            stagePos = self._solveGlobalStagePosition(pos)
            stagePath.append({'globalPos': stagePos, 'speed': speed, 'linear': linear, 'explanation': explanation})

        stage = self.parentDevice()
        return stage.movePath(stagePath)

    def approachDepth(self):
        """Return the global depth where the electrode should move to when starting approach mode.

        This is defined as the sample surface + 100um.
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        if surface is None:
            raise ValueError("Surface depth has not been set.")
        return surface + self._opts['approachHeight']

    @property
    def cleanApproachHeight(self):
        return self._opts["cleanApproachHeight"]

    def depthBelowSurface(self):
        """Return the current depth of the pipette tip below the sample surface
        (positive values are below the surface).
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        return surface - self.globalPosition()[2]

    def globalDirection(self):
        """Return a global unit vector pointing in the direction of the pipette axis.
        """
        if self._globalDirection is None:
            pitch = self.pitchRadians()
            yaw = self.yawRadians()
            s = np.cos(pitch)
            self._globalDirection = np.array([s * np.cos(yaw), s * np.sin(yaw), -np.sin(pitch)])
        return self._globalDirection.copy()

    def localDirection(self):
        """Return a local unit vector pointing in the direction of the pipette axis.
        """
        if self._localDirection is None:
            pitch = self.pitchRadians()
            self._localDirection = np.array([np.cos(pitch), 0, -np.sin(pitch)])
        return self._localDirection.copy()

    def positionAtDepth(self, depth, start=None):
        """Return the global position at *depth* that lies along the axis of the pipette.

        If *start* is given, then the pipette axis is assumed to go through this global position rather than
        its current position.
        """
        if start is None:
            start = self.globalPosition()
        axis = self.globalDirection()
        dz = depth - start[2]
        dist = dz / axis[2]
        return start + dist * axis

    def advance(self, depth, speed):
        """Move the electrode along its axis until it reaches the specified
        (global) depth.
        """
        pos = self.positionAtDepth(depth)
        return self._moveToGlobal(pos, speed)

    def retractFromSurface(self, speed='slow'):
        """Retract the pipette along its axis until it is above the slice surface.
        """
        depth = self.globalPosition()[2]
        appDepth = self.approachDepth()
        if depth < appDepth:
            return self.advance(appDepth, speed=speed)

    @future_wrap
    def stepwiseAdvance(self, depth: float, maxSpeed: float = 10e-6, interval: float = 5, _future=None):
        """Retract/advance in 1µm steps, allowing for manual user movements"""
        initial_direction = None
        self.keepOnStepping = True
        while self.keepOnStepping:
            pos = self.globalPosition()
            goal = self.positionAtDepth(depth)
            direction = goal - pos
            if initial_direction is None:
                initial_direction = np.sign(direction[2])
            if np.sign(direction[2]) != initial_direction:
                break  # overshot
            delta = 1e-6
            distance = np.linalg.norm(direction)
            step = pos + delta * direction / distance
            _future.waitFor(self._moveToGlobal(step, speed=maxSpeed, linear=True))
            if distance <= delta:
                break
            _future.sleep(interval)

    @future_wrap
    def wiggle(self, speed, radius, repetitions, duration, pipette_direction=None, extra=None, _future=None):
        if pipette_direction is None:
            pipette_direction = self.globalDirection()

        def random_wiggle_direction():
            """pick a random point on a circle perpendicular to the pipette axis"""
            while np.linalg.norm(vec := np.cross(pipette_direction, np.random.uniform(-1, 1, size=3))) == 0:
                pass  # prevent division by zero
            return vec / np.linalg.norm(vec)

        pos = np.array(self.globalPosition())
        prev_dir = random_wiggle_direction()
        for _ in range(repetitions):
            with contextlib.ExitStack() as stack:
                if extra is not None:
                    stack.enter_context(extra())
                start = ptime.time()
                while ptime.time() - start < duration:
                    while np.dot(direction := random_wiggle_direction(), prev_dir) > 0:
                        pass  # ensure different direction from previous
                    _future.waitFor(self._moveToGlobal(pos=pos + radius * direction, speed=speed))
                    prev_dir = direction
                _future.waitFor(self._moveToGlobal(pos=pos, speed=speed))

    def globalPosition(self):
        """Return the position of the electrode tip in global coordinates.

        Note: the position in local coordinates is always [0, 0, 0].
        """
        return self.mapToGlobal([0, 0, 0])

    def _moveToGlobal(self, pos, speed, **kwds):
        """Move the electrode tip directly to the given position in global coordinates.
        WARNING: This method does _not_ implement any motion planning.
        """
        self.sigMoveRequested.emit(self, pos, speed, kwds)
        stagePos = self._solveGlobalStagePosition(pos)
        stage = self.parentDevice()
        try:
            return stage.moveToGlobal(stagePos, speed, **kwds)
        except Exception:
            print(f"Error moving {self} to global position {pos!r}:")
            raise

    def _solveGlobalStagePosition(self, pos):
        """Return global stage position required in order to move pipette to a global position.
        """
        dif = np.asarray(pos) - np.asarray(self.globalPosition())
        stage = self.parentDevice()
        spos = np.asarray(stage.globalPosition())
        return spos + dif

    def _solveMyGlobalPosition(self, pos):
        """Return the global position of the pipette tip when the stage is at the given global position.
        """
        dif = np.asarray(pos) - np.asarray(self.parentDevice().globalPosition())
        return np.asarray(self.globalPosition()) + dif

    def _moveToLocal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in local coordinates.
        WARNING: This method does _not_ implement any motion planning.
        """
        return self._moveToGlobal(self.mapToGlobal(pos), speed, linear=linear)

    def setTarget(self, target):
        self.target = np.array(target)
        self.writeConfigFile({'targetGlobalPosition': list(self.target)}, 'target')
        self.sigTargetChanged.emit(self, self.target)

    def targetPosition(self):
        if self.target is None:
            raise RuntimeError(f"No target defined for {self.name()}")
        return self.target

    def hideMarkers(self, hide):
        for iface in self._camInterfaces.keys():
            iface.hideMarkers(hide)

    def focusTip(self, speed='fast', raiseErrors=False):
        pos = self.globalPosition()
        future = self.scopeDevice().setGlobalPosition(pos, speed=speed)
        if raiseErrors:
            future.raiseErrors("Focus on pipette tip failed ({error}); requested from:\n{stack})")
        return future

    def focusTarget(self, speed='fast', raiseErrors=False):
        pos = self.targetPosition()
        future = self.scopeDevice().setGlobalPosition(pos, speed=speed)
        if raiseErrors:
            future.raiseErrors("Focus on pipette target failed ({error}); requested from:\n{stack})")
        return future

    def positionChanged(self):
        self.moveTimer.start(500)
        if self.moving is False:
            self.moving = True
            self.sigMoveStarted.emit(self, self.globalPosition())

    def positionChangeFinished(self):
        self.moveTimer.stop()
        self.moving = False
        self.sigMoveFinished.emit(self, self.globalPosition())

    def getRecordingChambers(self) -> List[RecordingChamber]:
        """Return a list of RecordingChamber instances that are associated with this Pipette (see
        'recordingChambers' config option).
        """
        man = getManager()
        return [man.getDevice(d) for d in self.config.get('recordingChambers', [])]

    def startRecording(self):
        """Return an object that records all motion updates from this pipette
        """
        return PipetteRecorder(self)

    def findNewPipette(self):
        from acq4.devices.Pipette.calibration import findNewPipette
        future = findNewPipette(self, self.imagingDevice(), self.scopeDevice())
        self._last_calibration_future = future  # keep for easy debugging of calibration algorithm
        return future


class PipetteRecorder:
    def __init__(self, pip):
        self.pip = pip
        self.events = []

        self.pip.sigGlobalTransformChanged.connect(self.recordPos, Qt.Qt.DirectConnection)
        self.pip.sigMoveStarted.connect(self.recordMoveStarted, Qt.Qt.DirectConnection)
        self.pip.sigMoveFinished.connect(self.recordMoveFinished, Qt.Qt.DirectConnection)
        self.pip.sigMoveRequested.connect(self.recordMoveRequested, Qt.Qt.DirectConnection)

        self.newEvent('init',
                      {'position': tuple(self.pip.globalPosition()), 'direction': tuple(self.pip.globalDirection())})

    def recordPos(self):
        self.newEvent('position_change', {'position': tuple(self.pip.globalPosition())})

    def recordMoveStarted(self, pip, pos):
        self.newEvent('move_start', {'position': tuple(pos)})

    def recordMoveFinished(self, pip, pos):
        self.newEvent('move_stop', {'position': tuple(pos)})

    def recordMoveRequested(self, pip, pos, speed, opts):
        self.newEvent('move_request', {'position': tuple(pos), 'speed': speed, 'opts': opts})

    def newEvent(self, eventType, eventData):
        newEv = dict([
            ('device', self.pip.name()),
            ('event_time', ptime.time()),
            ('event', eventType),
        ])
        if eventData is not None:
            newEv.update(eventData)
        self.events.append(newEv)

    def stop(self):
        self.pip.sigGlobalTransformChanged.disconnect(self.recordPos)
        self.pip.sigMoveStarted.disconnect(self.recordMoveStarted)
        self.pip.sigMoveFinished.disconnect(self.recordMoveFinished)
        self.pip.sigMoveRequested.disconnect(self.recordMoveRequested)

    def store(self, filename):
        json.dump(self.events, open(f'{filename}.json', 'w'))


class PipetteCamModInterface(CameraModuleInterface):
    """**DEPRECATED** use MultiPatch module instead

    Implements user interface for Pipette.
    """
    canImage = False

    def __init__(self, dev: "Pipette", mod, showUi=True):
        CameraModuleInterface.__init__(self, dev, mod)
        self._haveTarget = False
        self._showUi = showUi

        self.ui = CamModTemplate()
        self.ctrl = Qt.QWidget()
        self.ui.setupUi(self.ctrl)

        self.calibrateAxis = Axis([0, 0], 0, inverty=False)
        self.calibrateAxis.setZValue(5000)
        mod.addItem(self.calibrateAxis)
        self.calibrateAxis.setVisible(False)

        self.centerArrow = pg.ArrowItem()
        self.centerArrow.setZValue(5000)
        mod.addItem(self.centerArrow)

        self.target = Target()
        self.target.setZValue(5000)
        mod.addItem(self.target)
        self.target.setVisible(False)

        # decide how / whether to add a label for the target
        basename = dev.name().rstrip('0123456789')
        self.pipetteNumber = dev.name()[len(basename):]

        showLabel = False
        if basename != dev.name():
            # If this device looks like "Name00" and another device has the same
            # prefix, then we will label all targets with their device numbers.
            for devname in getManager().listDevices():
                if devname.startswith(basename):
                    showLabel = True
                    break
        if showLabel:
            self._updateTargetLabel()

        self.depthTarget = Target(movable=False)
        mod.getDepthView().addItem(self.depthTarget)
        self.depthTarget.setVisible(False)

        self.depthArrow = pg.ArrowItem(angle=180 - dev.yawAngle())
        mod.getDepthView().addItem(self.depthArrow)

        # self.ui.setOrientationBtn.toggled.connect(self.setOrientationToggled)
        self.ui.setOrientationBtn.setEnabled(False)
        mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        dev.sigGlobalTransformChanged.connect(self.transformChanged)
        dev.scopeDevice().sigGlobalTransformChanged.connect(self.focusChanged)
        dev.sigTargetChanged.connect(self.targetChanged)
        self.calibrateAxis.sigRegionChangeFinished.connect(self.calibrateAxisChanged)
        self.calibrateAxis.sigRegionChanged.connect(self.calibrateAxisChanging)
        self.ui.homeBtn.clicked.connect(self.homeClicked)
        self.ui.searchBtn.clicked.connect(self.searchClicked)
        self.ui.idleBtn.clicked.connect(self.idleClicked)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)
        self.ui.targetBtn.clicked.connect(self.targetClicked)
        self.ui.approachBtn.clicked.connect(self.approachClicked)
        self.ui.autoCalibrateBtn.clicked.connect(self.autoCalibrateClicked)
        self.ui.getRefBtn.clicked.connect(self.getRefFramesClicked)
        self.ui.aboveTargetBtn.clicked.connect(self.aboveTargetClicked)
        self.target.sigPositionChangeFinished.connect(self.targetDragged)

        self.transformChanged()
        self.targetChanged(dev, dev.targetPosition())
        self.updateCalibrateAxis()

    def setOrientationToggled(self):
        self.updateCalibrateAxis()
        self.calibrateAxis.setVisible(self.ui.setOrientationBtn.isChecked())

    def selectedSpeed(self):
        return 'fast' if self.ui.fastRadio.isChecked() else 'slow'

    def hideMarkers(self, hide):
        self.centerArrow.setVisible(not hide)
        self.target.setVisible(not hide and self._haveTarget)

    def sceneMouseClicked(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        if self.ui.setCenterBtn.isChecked():
            self.ui.setCenterBtn.setChecked(False)
            pos = self.mod().getView().mapSceneToView(ev.scenePos())
            self.calibrateAxis.setPos(pos)

        elif self.ui.setTargetBtn.isChecked():
            pos = self.mod().getView().mapSceneToView(ev.scenePos())
            z = self.getDevice().scopeDevice().getFocusDepth()
            self.setTargetPos(pos, z)
            self.target.setFocusDepth(z)

    def setTargetPos(self, pos, z):
        self.dev().setTarget((pos.x(), pos.y(), z))

    def targetChanged(self, dev, pos):
        self.target.setPos(pg.Point(pos[:2]))
        self.target.setDepth(pos[2])
        self.depthTarget.setPos(Point(0, pos[2]))
        self.target.setVisible(True)
        self._haveTarget = True
        self.depthTarget.setVisible(True)
        self.ui.targetBtn.setEnabled(True)
        self.ui.approachBtn.setEnabled(True)
        self.ui.setTargetBtn.setChecked(False)
        self.focusChanged()

    def targetDragged(self):
        z = self.getDevice().scopeDevice().getFocusDepth()
        self.setTargetPos(self.target.pos(), z)
        self.target.setFocusDepth(z)

    def transformChanged(self):
        # manipulator's global transform has changed; update the center arrow and orientation axis
        pos, angle = self.analyzeTransform()

        self.centerArrow.setPos(pos[0], pos[1])
        self.centerArrow.setStyle(angle=180 - angle)
        # self.depthLine.setValue(pos[2])
        self.depthArrow.setPos(0, pos[2])

        if self.target.label() is not None:
            self._updateTargetLabel()

    def _updateTargetLabel(self):
        num = self.pipetteNumber
        dev = self.getDevice()
        angle = dev.yawAngle() + 180
        offset = 16 * np.cos(angle * np.pi / 180), 16 * np.sin(angle * np.pi / 180)
        self.target.setLabel(num, {'offset': offset, 'anchor': (0.5, 0.5)})

    def analyzeTransform(self):
        """Return the position and yaw angle of the device transform
        """
        dev = self.getDevice()
        pos = dev.mapToGlobal([0, 0, 0])
        x = dev.mapToGlobal([1, 0, 0])
        p1 = pg.Point(x[:2])
        p2 = pg.Point(pos[:2])
        p3 = pg.Point(1, 0)
        angle = (p1 - p2).angle(p3)
        if angle is None:
            angle = 0

        return pos, angle

    def updateCalibrateAxis(self):
        pos, angle = self.analyzeTransform()
        with pg.SignalBlock(self.calibrateAxis.sigRegionChangeFinished, self.calibrateAxisChanged):
            self.calibrateAxis.setPos(pos[:2])
            self.calibrateAxis.setAngle(angle)

    def focusChanged(self):
        try:
            tdepth = self.dev().targetPosition()[2]
        except RuntimeError:
            return
        fdepth = self.dev().scopeDevice().getFocusDepth()
        self.target.setFocusDepth(fdepth)

    def calibrateAxisChanging(self):
        pos = self.calibrateAxis.pos()
        angle = self.calibrateAxis.angle()

        self.centerArrow.setPos(pos[0], pos[1])
        self.centerArrow.setStyle(angle=180 - angle)

    def calibrateAxisChanged(self):
        pos = self.calibrateAxis.pos()
        angle = self.calibrateAxis.angle()
        size = self.calibrateAxis.size()
        dev = self.getDevice()
        z = dev.scopeDevice().getFocusDepth()

        # first orient the parent stage
        dev.setCalibratedOrientation(yaw=angle)

        # next set our position offset
        pos = [pos.x(), pos.y(), z]
        dev.resetGlobalPosition(pos)

    def controlWidget(self):
        if self._showUi:
            return self.ctrl
        else:
            return None

    def boundingRect(self):
        return None

    def quit(self):
        for item in self.calibrateAxis, self.centerArrow, self.depthArrow:
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)

    def homeClicked(self):
        self.getDevice().goHome(self.selectedSpeed())

    def searchClicked(self):
        self.getDevice().goSearch(self.selectedSpeed())

    def idleClicked(self):
        self.getDevice().goIdle(self.selectedSpeed())

    def setTargetToggled(self, b):
        if b:
            self.ui.setCenterBtn.setChecked(False)

    def setCenterToggled(self, b):
        if b:
            self.ui.setTargetBtn.setChecked(False)

    def targetClicked(self):
        self.getDevice().goTarget(self.selectedSpeed())

    def approachClicked(self):
        self.getDevice().goApproach(self.selectedSpeed())

    def autoCalibrateClicked(self):
        pip = self.getDevice()
        pos = pip.tracker.findTipInFrame()
        tip_future = pip.setTipOffsetIfAcceptable(pos)
        tip_future.onFinish(self._handleTipPositionSet)

    def _handleTipPositionSet(self, future):
        success = future.getResult()
        if not success:
            return self.autoCalibrateClicked()

    def getRefFramesClicked(self):
        dev = self.getDevice()
        zrange = dev.config.get('referenceZRange', None)
        zstep = dev.config.get('referenceZStep', None)
        dev.tracker.takeReferenceFrames(zRange=zrange, zStep=zstep)

    def aboveTargetClicked(self):
        self.getDevice().goAboveTarget(self.selectedSpeed())


class Axis(pg.ROI):
    """Used for calibrating pipette position and orientation.
    """

    def __init__(self, pos, angle, inverty):
        arrow = pg.makeArrowPath(headLen=20, tipAngle=30, tailLen=60, tailWidth=2).translated(-84, 0)
        tr = Qt.QTransform()
        tr.rotate(180)
        self._path = tr.map(arrow)
        tr.rotate(90)
        self._path |= tr.map(arrow)
        self.pxLen = [1, 1]
        self._bounds = None

        pg.ROI.__init__(self, pos, angle=angle, invertible=True, movable=False)
        if inverty:
            self.setSize([1, -1])
        else:
            self.setSize([1, 1])
        self.addRotateHandle([1, 0], [0, 0])
        self.addScaleHandle([0, 1], [0, 0])
        self.addTranslateHandle([0, 0])
        self.viewTransformChanged()

        self.x = pg.TextItem('X', anchor=(0.5, 0.5))
        self.x.setParentItem(self)
        self.y = pg.TextItem('Y', anchor=(0.5, 0.5))
        self.y.setParentItem(self)

        self.sigRegionChanged.connect(self.viewTransformChanged)

    def viewTransformChanged(self):
        if not self.isVisible():
            return
        w = self.pixelLength(pg.Point(1, 0))
        if w is None:
            self._pxLen = [None, None]
            return
        h = self.pixelLength(pg.Point(0, 1))
        if self.size()[1] < 0:
            h = -h
        self._pxLen = [w, h]
        self.blockSignals(True)
        try:
            self.setSize([w * 50, h * 50])
        finally:
            self.blockSignals(False)
        self.updateText()
        self._bounds = None
        self.prepareGeometryChange()

    def updateText(self):
        w, h = self._pxLen
        if w is None:
            return
        self.x.setPos(w * 100, 0)
        self.y.setPos(0, h * 100)

    def boundingRect(self):
        if self._bounds is None:
            w, h = self._pxLen
            if w is None:
                return Qt.QRectF()
            w = w * 100
            h = abs(h * 100)
            self._bounds = Qt.QRectF(-w, -h, w * 2, h * 2)
        return self._bounds

    def setVisible(self, v):
        pg.ROI.setVisible(self, v)
        if v is True:
            self.viewTransformChanged()

    def paint(self, p, *args):
        p.setRenderHint(p.Antialiasing)
        w, h = self._pxLen
        p.setPen(pg.mkPen('y'))
        p.setBrush(pg.mkBrush(255, 255, 0, 100))
        p.scale(w, h)
        p.drawPath(self._path)

    def setAngle(self, angle, update=True, **kwds):
        if self.state['angle'] == angle:
            return
        pg.ROI.setAngle(self, angle, update=update, **kwds)


class PipetteDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.posLabelLayout = Qt.QHBoxLayout()
        self.layout.addLayout(self.posLabelLayout, 0, 0)

        self.posLabels = [Qt.QLabel(), Qt.QLabel(), Qt.QLabel()]
        for l in self.posLabels:
            self.posLabelLayout.addWidget(l)

        self.dev.sigGlobalTransformChanged.connect(self.pipetteMoved)
        self.pipetteMoved()

    def pipetteMoved(self):
        pos = self.dev.globalPosition()
        for i in range(3):
            self.posLabels[i].setText("%0.3f mm" % (pos[i] * 1e3))
