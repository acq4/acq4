# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import division

import pickle
from acq4.util import Qt
import numpy as np
import weakref

import acq4.pyqtgraph as pg
from acq4 import getManager
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from acq4.modules.Camera import CameraModuleInterface
from acq4.util.target import Target
from .tracker import PipetteTracker

CamModTemplate = Qt.importTemplate('.cameraModTemplate')


class Pipette(Device, OptomechDevice):
    """Represents a pipette or electrode attached to a motorized manipulator.

    This device provides a camera module interface for driving a motorized electrode holder:

    * Visually direct pipette tip via camera module
    * Automatically align pipette tip for diagonal approach to cells
    * Automatically calibrate pipette tip position (via Tracker)

    This device must be configured with a Stage as its parent.

    The local coordinate system of the device is configured such that the electrode is in the 
    x/z plane, pointing toward +x and -z (assuming the pitch is positive). The origin of the
    local coordinate system is at the tip of the pipette.

             \\ +z
              \\ |
         pitch \\|
    -x  <-------\\------> +x
                |\\
                | \\
               -z   \ - electrode tip


    Configuration options:

    * pitch: The angle of the pipette (in degrees) relative to the horizontal plane,
      Positive values point downward. This option must be specified in the configuration.
    * searchHeight: the distance to focus above the sample surface when searching for pipette tips. This
      should be about 1-2mm, emough to avoid collisions between the pipette tip and the sample during search.
      Default is 2 mm.
    * searchTipHeight: the distance above the sample surface to bring the (putative) pipette tip position
      when searching for new pipette tips. For low working-distance objectives, this should be about 0.5 mm less
      than *searchHeight* to avoid collisions between the tip and the objective during search.
      Default is 1.5 mm.
    * approachHeight: the distance to bring the pipette tip above the sample surface when beginning 
      a diagonal approach. Default is 100 um.
    * idleHeight: the distance to bring the pipette tip above the sample surface when in idle position
      Default is 1 mm.
    * idleDistance: the x/y distance from the global origin from which the pipette top should be placed
      in idle mode. Default is 7 mm.
    """

    sigTargetChanged = Qt.Signal(object, object)
    sigCalibrationChanged = Qt.Signal(object)

    # move start/finish are used for recording coarse movement information;
    # they are not emitted for every transform change.
    sigMoveStarted = Qt.Signal(object)
    sigMoveFinished = Qt.Signal(object)

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
        self.config = config
        self.moving = False
        self._scopeDev = None
        self._imagingDev = None
        self._stageOrientation = {'angle': 0, 'inverty': False}
        self._opts = {
            'searchHeight': config.get('searchHeight', 2e-3),
            'searchTipHeight': config.get('searchTipHeight', 1.5e-3),
            'approachHeight': config.get('approachHeight', 100e-6),
            'idleHeight': config.get('idleHeight', 1e-3),
            'idleDistance': config.get('idleDistance', 7e-3),
            'showCameraModuleUI': config.get('showCameraModuleUI', True),
        }
        parent = self.parentDevice()
        if not isinstance(parent, Stage):
            raise Exception("Pipette device requires some type of translation stage as its parent.")

        self._camInterfaces = weakref.WeakKeyDictionary()

        self.target = None

        cal = self.readConfigFile('calibration')

        self.offset = np.array(cal.get('offset', [0, 0, 0]))
        self._calibratedPitch = cal.get('pitch', None)
        self._calibratedYaw = cal.get('yaw', cal.get('angle', None))  # backward support for old 'angle' config key

        # timer used to emit sigMoveFinished when no motion is detected for a certain period 
        self.moveTimer = Qt.QTimer()
        self.moveTimer.timeout.connect(self.positionChangeFinished)
        self.sigGlobalTransformChanged.connect(self.positionChanged)

        self._updateTransform()

        self.tracker = PipetteTracker(self)
        deviceManager.declareInterface(name, ['pipette'], self)

        target = self.readConfigFile('target').get('targetGlobalPosition', None)
        if target is not None:
            self.setTarget(target)

    def savePosition(self, name, pos=None):
        """Store a position in global coordinates for later use.

        If no position is provided, then the current position of the pipette tip is used.
        """
        if pos is None:
            pos = self.globalPosition()

        cache = self.readConfigFile('stored_positions')
        cache[name] = list(pos)
        self.writeConfigFile(cache, 'stored_positions')

    def loadPosition(self, name, default=None):
        """Return a previously saved position.
        """
        cache = self.readConfigFile('stored_positions')
        return cache.get(name, default)

    def scopeDevice(self):
        if self._scopeDev is None:
            imdev = self.imagingDevice()
            self._scopeDev = imdev.scopeDev
        return self._scopeDev

    def imagingDevice(self):
        if self._imagingDev is None:
            man = getManager()
            name = self.config.get('imagingDevice', None)
            if name is None:
                cams = man.listInterfaces('camera')
                if len(cams) == 1:
                    name = cams[0]
                else:
                    raise Exception("Pipette requires either a single imaging device available (found %d) or 'imagingDevice' specified in its configuration." % len(cams))
            self._imagingDev = man.getDevice(name)
        return self._imagingDev

    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PipetteDeviceGui(self, win)

    def cameraModuleInterface(self, mod):
        if self._opts['showCameraModuleUI'] is False:
            return None
        iface = PipetteCamModInterface(self, mod)
        self._camInterfaces[iface] = None
        return iface

    def setCalibratedOrientation(self, yaw=None, pitch=None):
        """Set the orientation of the pipette relative to its parent coordinate system.

        The *yaw* angle specifies a rotation in degrees around the vertical (Z) axis, where 0 points
        in the direction of the parent's +X axis.

        The *pitch* angle specifies the downward angle (degrees) of the pipette relative to the horizontal plane.

        Setting the pipette orientation has two effects:
        * Motion planning uses this information to avoid dragging the pipette sideways through the sample
        * The local coordinate system of the Pipette device is rotated such that +X points
          in the direction of the pipette tip.

        """
        cal = self.readConfigFile('calibration')
        if yaw is not None:
            self._calibratedYaw = yaw
            cal['yaw'] = yaw
        if pitch is not None:
            self._calibratedPitch = pitch
            cal['pitch'] = pitch
        self.writeConfigFile(cal, 'calibration')

        self._updateTransform()

    def resetGlobalPosition(self, pos):
        """Set the device transform such that the pipette tip is located at the global position *pos*.

        This method is for recalibration; it does not physically move the device.
        """
        lpos = np.array(self.mapFromGlobal(pos))
        self.setOffset(self.offset + lpos)

    def setOffset(self, offset):
        self.offset = np.array(offset)
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(offset)
        self.writeConfigFile(cal, 'calibration')
        self._updateTransform()
        self.sigCalibrationChanged.emit(self)

    def _updateTransform(self):
        tr = pg.Transform3D()
        tr.rotate(self.yawAngle(), pg.Vector(0, 0, 1))
        # tr.rotate(self.pitchAngle(), pg.Vector(1, 0, 0))
        tr.translate(*self.offset)
        self.setDeviceTransform(tr)

    def saveCalibration(self):
        cal = self.readConfigFile('calibration')
        cal['offset'] = list(self.offset)
        cal['pitch'] = self._calibratedPitch
        cal['yaw'] = self._calibratedYaw
        self.writeConfigFile(cal, 'calibration')

    def yawAngle(self):
        """Return the yaw (azimuthal angle) of the electrode around the Z-axis in degrees.

        Value is returned in degrees such that an angle of 0 indicate the tip points along the positive x axis,
        and 90 points along the positive y axis.
        """
        if self._calibratedYaw is None:
            return self.config.get('yaw', 0)
        else:
            return self._calibratedYaw

    def pitchAngle(self):
        """Return the pitch of the electrode in degrees (angle relative to horizontal plane).

        For positive angles, the pipette tip points downward, toward -Z. 
        """
        if self._calibratedPitch is None:
            return self.config.get('pitch', 30)
        else:
            return self._calibratedPitch

    def yawRadians(self):
        return self.yawAngle() * np.pi / 180.

    def pitchRadians(self):
        return self.pitchAngle() * np.pi / 180.    

    def goHome(self, speed='fast'):
        """Extract pipette tip diagonally, then move stage to home position.
        """
        stage = self.parentDevice()
        stagePos = stage.globalPosition()
        stageHome = stage.homePosition()
        globalMove = np.asarray(stageHome) - np.asarray(stagePos) # this is how much electrode should move in global coordinates

        startPosGlobal = self.globalPosition()
        endPosGlobal = np.asarray(startPosGlobal) + globalMove  # this is where electrode should end up in global coordinates
        endPos = self.mapFromGlobal(endPosGlobal)  # and in local coordinates

        # define the path to take in local coordinates because that makes it
        # easier to do the boundary intersections
        homeAngle = np.arctan2(endPos[2], -endPos[0])
        if homeAngle > self.pitchRadians():
            # diagonal move to 
            dz = -endPos[0] * np.tan(self.pitchRadians())
            waypoint = self.mapToGlobal([endPos[0], 0, dz])
        else:
            dx = -endPos[2] / np.tan(self.pitchRadians())
            waypoint = self.mapToGlobal([dx, 0, endPos[2]])
            if dx > 0:  # in case home z position is below the current z pos.
                waypoint = None
        
        if waypoint is None:
            path = [(endPosGlobal, speed, False)]
        else:
            # sanity check
            for i in range(3):
                waypoint[i] = np.clip(waypoint[i], startPosGlobal[i], endPosGlobal[i])
            path = [
                (waypoint, speed, True),
                (endPosGlobal, speed, False),
            ]

        return self._movePath(path)

    def goSearch(self, speed='fast', distance=0):
        """Focus the microscope 2mm above the surface, then move the electrode 
        tip to 500um below the focal point of the microscope. 

        This position is used when searching for new electrodes.

        Set *distance* to adjust the search position along the pipette's x-axis. Positive values
        move the tip farther from the microscope center to reduce the probability of collisions.
        Negative values move the pipette past the center of the microscope to improve the
        probability of seeing the tip immediately. 
        """
        # Bring focus to 2mm above surface (if needed)
        scope = self.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        if surfaceDepth is None:
            raise Exception("Cannot determine search position; surface depth is not defined.")
        searchDepth = surfaceDepth + self._opts['searchHeight']

        cam = self.imagingDevice()
        focusDepth = cam.getFocusDepth()

        # move scope such that camera will be focused at searchDepth
        if focusDepth < searchDepth:
            scopeFocus = scope.getFocusDepth()
            scope.setFocusDepth(scopeFocus + searchDepth - focusDepth).wait(updates=True)

        # Here's where we want the pipette tip in global coordinates:
        globalTarget = cam.globalCenterPosition('roi')
        globalTarget[2] += self._opts['searchTipHeight'] - self._opts['searchHeight']

        # adjust for distance argument:
        localTarget = self.mapFromGlobal(globalTarget)
        localTarget[0] -= distance
        globalTarget = self.mapToGlobal(localTarget)

        return self._moveToGlobal(globalTarget, speed)

        # below is an implementation of a multi-step move to help avoid obstacles on the way to search position. This slows us down a lot and 
        # isn't terribly clever.

        # pos = self.globalPosition()
        # if np.linalg.norm(np.asarray(globalTarget) - pos) < 5e-3:
        #     raise Exception('"Search" position should only be used when electrode is far from objective.')

        # # compute intermediate position
        # localTarget = self.mapFromGlobal(globalTarget)
        # # local vector pointing in direction of electrode tip
        # evec = np.array([1., 0., -np.tan(self.pitch)])
        # evec /= np.linalg.norm(evec)
        # waypoint = localTarget - evec * self._opts['idleDistance']

        # path = [
        #     (self.mapToGlobal(waypoint), speed, False),
        #     (globalTarget, speed, True),
        # ]
        # return self._movePath(path)

    def goApproach(self, speed):
        """Move the electrode tip such that it is 100um above the sample surface with its
        axis aligned to the target. 
        """
        target = self.targetPosition()
        return self._movePath(self._approachPath(target, speed))

    def goIdle(self, speed='fast'):
        """Move the electrode tip to the outer edge of the recording chamber, 1mm above the sample surface.

        NOTE: this method assumes that (0, 0) in global coordinates represents the center of the recording
        chamber.
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        if surface is None:
            raise Exception("Surface depth has not been set.")

        # we want to land 1 mm above sample surface
        idleDepth = surface + self._opts['idleHeight']

        # If the tip is below idle depth, bring it up along the axis of the electrode.
        pos = self.globalPosition()
        if pos[2] < idleDepth:
            self.advance(idleDepth, speed)

        # From here, move directly to idle position
        angle = self.yawRadians()
        ds = self._opts['idleDistance']  # move to 7 mm from center
        globalIdlePos = -ds * np.cos(angle), -ds * np.sin(angle), idleDepth
        self._moveToGlobal(globalIdlePos, speed)

    def _movePath(self, path):
        # move along a path defined in global coordinates. 
        # Format is [(pos, speed, linear), ...]
        # returns the movefuture of the last move.
        stagePath = []
        for pos, speed, linear in path:
            stagePos = self._solveGlobalStagePosition(pos)
            stagePath.append({'globalPos': stagePos, 'speed': speed, 'linear': linear})

        stage = self.parentDevice()
        return stage.movePath(stagePath)
    
    def _approachPath(self, target, speed):
        # Return steps (in global coords) needed to move to approach position
        stbyDepth = self.approachDepth()
        pos = self.globalPosition()

        # steps are in global coordinates.
        path = []

        # If tip is below the surface, then first pull out slowly along pipette axis
        if pos[2] < stbyDepth:
            dz = stbyDepth - pos[2]
            dx = -dz / np.tan(self.pitchRadians())
            last = np.array([dx, 0., dz])
            path.append([self.mapToGlobal(last), 100e-6, True])  # slow removal from sample
        else:
            last = np.array([0., 0., 0.])

        # local vector pointing in direction of electrode tip
        evec = np.array([1., 0., -np.tan(self.pitchRadians())])
        evec /= np.linalg.norm(evec)

        # target in local coordinates
        ltarget = self.mapFromGlobal(target)

        # compute approach position (axis aligned to target, at standby depth or higher)
        dz2 = max(0, stbyDepth - target[2])
        dx2 = -dz2 / np.tan(self.pitchRadians())
        stby = ltarget + np.array([dx2, 0., dz2])

        # compute intermediate position (point along approach axis that is closest to the current position)
        targetToTip = last - ltarget
        targetToStby = stby - ltarget
        targetToStby /= np.linalg.norm(targetToStby)
        closest = ltarget + np.dot(targetToTip, targetToStby) * targetToStby

        if np.linalg.norm(stby - last) > 1e-6:
            if (closest[2] > stby[2]) and (np.linalg.norm(stby - closest) > 1e-6):
                path.append([self.mapToGlobal(closest), speed, True])
            path.append([self.mapToGlobal(stby), speed, True])

        return path

    def goTarget(self, speed):
        target = self.targetPosition()
        pos = self.globalPosition()
        if np.linalg.norm(np.asarray(target) - pos) < 1e-7:
            return
        path = self._approachPath(target, speed)
        path.append([target, 100e-6, True])
        return self._movePath(path)

    def approachDepth(self):
        """Return the global depth where the electrode should move to when starting approach mode.

        This is defined as the sample surface + 100um.
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        if surface is None:
            raise Exception("Surface depth has not been set.")
        return surface + self._opts['approachHeight']

    def depthBelowSurface(self):
        """Return the current depth of the pipette tip below the sample surface
        (positive values are below the surface).
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        return surface - self.globalPosition()[2]

    def globalDirection(self):
        """Return a global uinit vector pointing in the direction of the pipette axis.
        """
        o = np.array(self.globalPosition())
        dz = -1.0
        dx = -dz / np.tan(self.pitchRadians())
        p = self.mapToGlobal(np.array([dx, 0, dz]))
        v = p - o
        return v / np.linalg.norm(v)

    def advance(self, depth, speed):
        """Move the electrode along its axis until it reaches the specified
        (global) depth.
        """
        pos = self.globalPosition()
        dz = depth - pos[2]
        dx = -dz / np.tan(self.pitchRadians())
        return self._moveToLocal([dx, 0, dz], speed, linear=True)

    def retractFromSurface(self, speed='slow'):
        """Retract the pipette along its axis until it is above the slice surface.
        """
        depth = self.globalPosition()[2]
        appDepth = self.approachDepth()
        if depth < appDepth:
            return self.advance(appDepth, speed=speed)
        else:
            # just to make sure we always return a Future
            return self.advance(depth, speed=speed)

    def globalPosition(self):
        """Return the position of the electrode tip in global coordinates.

        Note: the position in local coordinates is always [0, 0, 0].
        """
        return self.mapToGlobal([0, 0, 0])

    def _moveToGlobal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in global coordinates.
        This method does _not_ implement any motion planning.
        """
        stagePos = self._solveGlobalStagePosition(pos)
        stage = self.parentDevice()
        return stage.moveToGlobal(stagePos, speed, linear=linear)

    def _solveGlobalStagePosition(self, pos):
        """Return global stage position required in order to move pipette to a global position.
        """
        dif = np.asarray(pos) - np.asarray(self.globalPosition())
        stage = self.parentDevice()
        spos = np.asarray(stage.globalPosition())
        return spos + dif

    def _moveToLocal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in local coordinates.
        This method does _not_ implement any motion planning.
        """
        return self._moveToGlobal(self.mapToGlobal(pos), speed, linear=linear)

    def goAboveTarget(self, speed):
        """Move the pipette tip to be centered over the target in x/y, and 100 um above
        the sample surface in z. 

        This position is used to recalibrate the pipette immediately before going to approach.
        """
        scope = self.scopeDevice()
        waypoint1, waypoint2 = self.aboveTargetPath()

        pfut = self._moveToGlobal(waypoint1, speed)
        sfut = scope.setGlobalPosition(waypoint2)
        pfut.wait(updates=True)
        self._moveToGlobal(waypoint2, 'slow').wait(updates=True)
        sfut.wait(updates=True)

    def aboveTargetPath(self):
        """Return the path to the "above target" recalibration position.

        The path has 2 waypoints:

        1. 100 um away from the second waypoint, on a diagonal approach. This is meant to normalize the hysteresis
           at the second waypoint. 
        2. This position is centered on the target, a small distance above the sample surface.
        """
        target = self.targetPosition()

        # will recalibrate 50 um above surface
        scope = self.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        waypoint2 = np.array(target)
        waypoint2[2] = surfaceDepth + 50e-6

        # Need to arrive at this point via approach angle to correct for hysteresis
        lwp = self.mapFromGlobal(waypoint2)
        dz = 100e-6
        lwp[2] += dz
        lwp[0] -= dz / np.tan(self.pitchRadians())
        waypoint1 = self.mapToGlobal(lwp)

        return waypoint1, waypoint2

    def advanceTowardTarget(self, distance, speed='slow'):
        target = self.targetPosition()
        pos = self.globalPosition()
        dif = target - pos
        unit = dif / (dif**2).sum()**0.5
        waypoint = pos + distance * unit
        return self._moveToGlobal(waypoint, speed, linear=True)

    def startAdvancing(self, speed):
        """Begin moving the pipette at a constant speed along its axis.

        Positive speeds advance, negative speeds retract.
        """
        stage = self.parentDevice()
        vel = [speed * np.cos(self.pitchRadians()), 0, speed * -np.sin(self.pitchRadians())]
        a = self.mapToParentDevice([0, 0, 0])
        b = self.mapToParentDevice(vel)
        stage.startMoving([b[0]-a[0], b[1]-a[1], b[2]-a[2]])

    def retract(self, distance, speed='slow'):
        """Retract the pipette a specified distance along its axis.
        """
        dz = distance * np.sin(self.pitchRadians())
        dx = -distance * np.cos(self.pitchRadians())
        return self._moveToLocal([dx, 0, dz], speed, linear=True) 

    def setTarget(self, target):
        self.target = np.array(target)
        self.writeConfigFile({'targetGlobalPosition': list(self.target)}, 'target')
        self.sigTargetChanged.emit(self, self.target)

    def targetPosition(self):
        if self.target is None:
            raise RuntimeError("No target defined for %s" % self.name())
        return self.target

    def hideMarkers(self, hide):
        for iface in self._camInterfaces.keys():
            iface.hideMarkers(hide)

    def focusTip(self, speed='slow'):
        pos = self.globalPosition()
        self.scopeDevice().setGlobalPosition(pos, speed=speed)

    def focusTarget(self, speed='slow'):
        pos = self.targetPosition()
        self.scopeDevice().setGlobalPosition(pos, speed=speed)

    def positionChanged(self):
        self.moveTimer.start(500)
        if self.moving is False:
            self.moving = True
            self.sigMoveStarted.emit(self)

    def positionChangeFinished(self):
        self.moveTimer.stop()
        self.moving = False
        self.sigMoveFinished.emit(self)


class PipetteCamModInterface(CameraModuleInterface):
    """Implements user interface for Pipette.
    """
    canImage = False

    def __init__(self, dev, mod):
        CameraModuleInterface.__init__(self, dev, mod)
        self._haveTarget = False

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
        showLabel = False
        if basename != dev.name():
            # If this device looks like "Name00" and another device has the same
            # prefix, then we will label all targets with their device numbers.
            for devname in getManager().listDevices():
                if devname.startswith(basename):
                    showLabel = True
                    break
        if showLabel:
            num = dev.name()[len(basename):]
            self.target.setLabel(num)
            self.target.setLabelAngle(dev.yawAngle())

        self.depthTarget = Target(movable=False)
        mod.getDepthView().addItem(self.depthTarget)
        self.depthTarget.setVisible(False)

        self.depthArrow = pg.ArrowItem(angle=-dev.pitchAngle())
        mod.getDepthView().addItem(self.depthArrow)

        self.ui.setOrientationBtn.toggled.connect(self.setOrientationToggled)
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
        self.target.sigDragged.connect(self.targetDragged)

        self.transformChanged()

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
        self.depthTarget.setPos(0, pos[2])
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
        self.centerArrow.setStyle(angle=180-angle)
        # self.depthLine.setValue(pos[2])
        self.depthArrow.setPos(0, pos[2])

        dev = self.getDevice()
        yaw = dev.yawAngle()
        self.target.setLabelAngle(yaw)

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
        self.centerArrow.setStyle(angle=180-angle)

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
        return self.ctrl

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
        self.getDevice().tracker.autoCalibrate()

    def getRefFramesClicked(self):
        self.getDevice().tracker.takeReferenceFrames()

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
            self.setSize([w*50, h*50])
        finally:
            self.blockSignals(False)
        self.updateText()
        self._bounds = None
        self.prepareGeometryChange()

    def updateText(self):
        w, h = self._pxLen
        if w is None:
            return
        self.x.setPos(w*100, 0)
        self.y.setPos(0, h*100)

    def boundingRect(self):
        if self._bounds is None:
            w, h = self._pxLen
            if w is None:
                return Qt.QRectF()
            w = w * 100
            h = abs(h * 100)
            self._bounds = Qt.QRectF(-w, -h, w*2, h*2)
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

    def setAngle(self, angle):
        if self.state['angle'] == angle:
            return
        pg.ROI.setAngle(self, angle)


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
            self.posLabels[i].setText("%0.3g um" % (pos[i] * 1e6))
    
