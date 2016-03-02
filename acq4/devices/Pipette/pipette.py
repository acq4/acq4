# -*- coding: utf-8 -*-
from __future__ import division

import pickle
from PyQt4 import QtCore, QtGui
import numpy as np

import acq4.pyqtgraph as pg
from acq4 import getManager
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from acq4.modules.Camera import CameraModuleInterface
from .cameraModTemplate import Ui_Form as CamModTemplate
from .tracker import PipetteTracker


class Pipette(Device, OptomechDevice):
    """Represents a pipette or electrode attached to a motorized manipulator.

    This device provides a camera module interface for driving a motorized electrode holder:

    * Visually direct pipette tip via camera module
    * Automatically align pipette tip for diagonal approach to cells
    * Automatically calibrate pipette tip position (via Tracker)

    This device must be configured with a Stage as its parent.

    The local coordinate system of the device is configured such that the electrode is in the 
    x/z plane, pointing toward +x and -z (assuming the pitch is positive). 

             \\ +z
              \\ |
         pitch \\|
    -x  <-------\\------> +x
                |\\
                | \\
               -z   \ - electrode tip


    Configuration options:

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
    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
        self._scopeDev = deviceManager.getDevice(config['scopeDevice'])
        self._stageOrientation = {'angle': 0, 'inverty': False}
        self._opts = {
            'searchHeight': config.get('searchHeight', 2e-3),
            'searchTipHeight': config.get('searchTipHeight', 1.5e-3),
            'approachHeight': config.get('approachHeight', 100e-6),
            'idleHeight': config.get('idleHeight', 1e-3),
            'idleDistance': config.get('idleDistance', 7e-3),
        }
        parent = self.parentDevice()
        assert isinstance(parent, Stage)
        self.pitch = parent.pitch * np.pi / 180.

        cal = self.readConfigFile('calibration')
        if cal != {}:
            self.setStageOrientation(cal['angle'], cal['inverty'])
            self.setDeviceTransform(cal['transform'])

        self.tracker = PipetteTracker(self)

    def scopeDevice(self):
        return self._scopeDev

    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None

    def cameraModuleInterface(self, mod):
        return PipetteCamModInterface(self, mod)

    def setStageOrientation(self, angle, inverty):
        tr = pg.SRTTransform3D(self.parentDevice().baseTransform())
        tr.setScale(1, -1 if inverty else 1)
        tr.setRotate(angle)
        self.parentDevice().setBaseTransform(tr)

        cal = self.readConfigFile('calibration')
        cal['angle'] = angle
        cal['inverty'] = inverty
        self._stageOrientation = cal
        self.writeConfigFile(cal, 'calibration')

    def setDeviceTransform(self, tr):
        OptomechDevice.setDeviceTransform(self, tr)

        cal = self.readConfigFile('calibration')
        cal['transform'] = pg.SRTTransform3D(tr)
        self.writeConfigFile(cal, 'calibration')

    def getYawAngle(self):
        """Return the yaw (azimuthal angle) of the electrode around the Z-axis.

        Value is returned in degrees such that an angle of 0 indicate the tip points along the positive x axis,
        and 90 points along the positive y axis.
        """
        return self._stageOrientation['angle']

    def goHome(self, speed='fast'):
        """Extract pipette tip diagonally, then move pipette far away from the objective.

        This method currently makes several assumptions:

        * The position [0, 0, 0] on the parent stage device is a suitable home position (usually true for MPC200 stages)
        * The electrode is aligned with the x/z plane of the parent stage
        """
        stage = self.parentDevice()
        # stage's home position in local coords
        # this assumes that [0, 0, 0] is a good home position, but 
        # eventually this needs to be more configurable..
        stagePos = stage.globalPosition()

        stageHome = stage.mapToGlobal(stage.mapFromStage([0, 0, 0]))
        globalMove = np.asarray(stageHome) - np.asarray(stagePos) # this is how much electrode should move in global coordinates

        startPosGlobal = self.globalPosition()
        endPosGlobal = np.asarray(startPosGlobal) + globalMove  # this is where electrode should end up in global coordinates
        endPos = self.mapFromGlobal(endPosGlobal)  # and in local coordinates

        # define the path to take in local coordiantes because that makes it
        # easier to to the boundary intersections
        homeAngle = np.arctan2(endPos[2], -endPos[0])
        if homeAngle > self.pitch:
            # diagonal move to 
            dz = -endPos[0] * np.tan(self.pitch)
            waypoint = self.mapToGlobal([endPos[0], 0, dz])
            path = [
                (waypoint, speed, True),
                # (endPosGlobal, speed, False)
            ]
        else:
            dx = -endPos[2] / np.tan(self.pitch)
            waypoint1 = self.mapToGlobal([dx, 0, endPos[2]])
            waypoint2 = self.mapToGlobal([endPos[0], 0, endPos[2]])
            path = [
                (waypoint1, speed, True),
                (waypoint2, speed, False),
                # (endPosGlobal, speed, False),
            ]

        self._movePath(path)

    def goSearch(self, speed='fast'):
        """Focus the microscope 2mm above the surface, then move the electrode 
        tip to 500um below the focal point of the microscope. 

        This position is used when searching for new electrodes.
        """
        # Bring focus to 2mm above surface (if needed)
        scope = self.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        if surfaceDepth is None:
            raise Exception("Cannot determine search position; surface depth is not defined.")
        searchDepth = surfaceDepth + self._opts['searchHeight']
        if scope.getFocusDepth() < searchDepth:
            scope.setFocusDepth(searchDepth).wait(updates=True)

        # Here's where we want the pipette tip in global coordinates:
        globalTarget = scope.mapToGlobal([0, 0, self._opts['searchTipHeight'] - self._opts['searchHeight']])
        pos = self.globalPosition()
        if np.linalg.norm(np.asarray(globalTarget) - pos) < 5e-3:
            raise Exception('"Search" position should only be used when electrode is far from objective.')

        # compute intermediate position
        localTarget = self.mapFromGlobal(globalTarget)
        # local vector pointing in direction of electrode tip
        evec = np.array([1., 0., -np.tan(self.pitch)])
        evec /= np.linalg.norm(evec)
        waypoint = localTarget - evec * self._opts['idleDistance']

        path = [
            (self.mapToGlobal(waypoint), speed, False),
            (globalTarget, speed, True),
        ]
        self._movePath(path)

    def goApproach(self, target, speed):
        """Move the electrode tip such that it is 100um above the sample surface with its
        axis aligned to the target. 
        """
        self._movePath(self._approachPath(target, speed))

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
        angle = self.getYawAngle() * np.pi / 180
        ds = self._opts['idleDistance']  # move to 7 mm from center
        globalIdlePos = -ds * np.cos(angle), -ds * np.sin(angle), idleDepth
        print(angle, ds, globalIdlePos, idleDepth)
        self._moveToGlobal(globalIdlePos, speed)

    def _movePath(self, path):
        # move along a path defined in global coordinates. 
        # Format is [(pos, speed, linear), ...]

        # Simplify path if possible
        pos = self.globalPosition()
        path2 = []
        for step in path:
            pos2 = np.asarray(step[0])
            if np.linalg.norm(pos2 - pos) > 1e-6:
                path2.append(step)
            pos = pos2

        for pos, speed, linear in path2:
            self._moveToGlobal(pos, speed, linear=linear).wait(updates=True)
    
    def _approachPath(self, target, speed):
        # Return steps (in global coords) needed to move to approach position
        stbyDepth = self.approachDepth()
        pos = self.globalPosition()

        # steps are in global coordinates.
        path = []

        # If tip is below the surface, then first pull out slowly along pipette axis
        if pos[2] < stbyDepth:
            dz = stbyDepth - pos[2]
            dx = -dz / np.tan(self.pitch)
            last = np.array([dx, 0., dz])
            path.append([self.mapToGlobal(last), 100e-6, True])  # slow removal from sample
        else:
            last = np.array([0., 0., 0.])

        # local vector pointing in direction of electrode tip
        evec = np.array([1., 0., -np.tan(self.pitch)])
        evec /= np.linalg.norm(evec)

        # target in local coordinates
        ltarget = self.mapFromGlobal(target)

        # compute approach position (axis aligned to target, at standby depth or higher)
        dz2 = max(0, stbyDepth - target[2])
        dx2 = -dz2 / np.tan(self.pitch)
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

    def goTarget(self, target, speed):
        pos = self.globalPosition()
        if np.linalg.norm(np.asarray(target) - pos) < 1e-7:
            return
        path = self._approachPath(target, speed)
        path.append([target, 100e-6, True])
        self._movePath(path)

    def approachDepth(self):
        """Return the global depth where the electrode should move to when starting approach mode.

        This is defined as the sample surface + 100um.
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        if surface is None:
            raise Exception("Surface depth has not been set.")
        return surface + self._opts['approachHeight']

    def advance(self, depth, speed):
        """Move the electrode along its axis until it reaches the specified
        (global) depth.
        """
        pos = self.globalPosition()
        dz = depth - pos[2]
        dx = -dz / np.tan(self.pitch)
        return self._moveToLocal([dx, 0, dz], speed, linear=True)

    def globalPosition(self):
        """Return the position of the electrode tip in global coordinates.

        Note: the position in local coordinates is always [0, 0, 0].
        """
        return self.mapToGlobal([0, 0, 0])

    def _moveToGlobal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in global coordinates.
        This method does _not_ implement any motion planning.
        """
        dif = np.asarray(pos) - np.asarray(self.globalPosition())
        stage = self.parentDevice()
        spos = np.asarray(stage.globalPosition())
        return stage.moveToGlobal(spos + dif, speed, linear=linear)

    def _moveToLocal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in local coordinates.
        This method does _not_ implement any motion planning.
        """
        return self._moveToGlobal(self.mapToGlobal(pos), speed, linear=linear)

    def goAboveTarget(self, target, speed):
        """Move the pipette tip to be centered over the target in x/y, and 100 um above
        the sample surface in z. 

        This position is used to recalibrate the pipette immediately before going to approach.
        """
        # will recalibrate 50 um above surface
        scope = self.scopeDevice()
        surfaceDepth = scope.getSurfaceDepth()
        waypoint2 = np.array(target)
        waypoint2[2] = surfaceDepth + 50e-6

        # Need to arrive at this point via approach angle to correct for hysteresis
        lwp = self.mapFromGlobal(waypoint2)
        dz = 100e-6
        lwp[2] += dz
        lwp[0] -= dz / np.tan(self.pitch)
        waypoint1 = self.mapToGlobal(lwp)

        pfut = self._moveToGlobal(waypoint1, speed)
        sfut = scope.setGlobalPosition(waypoint2)
        pfut.wait(updates=True)
        self._moveToGlobal(waypoint2, 'slow').wait(updates=True)
        sfut.wait(updates=True)


class PipetteCamModInterface(CameraModuleInterface):
    """Implements user interface for Pipette.
    """
    canImage = False

    def __init__(self, dev, mod):
        CameraModuleInterface.__init__(self, dev, mod)
        self._targetPos = None

        self.ui = CamModTemplate()
        self.ctrl = QtGui.QWidget()
        self.ui.setupUi(self.ctrl)

        cal = dev._stageOrientation
        self.calibrateAxis = Axis([0, 0], 0, inverty=cal['inverty'])
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
            self.target.setLabelAngle(dev.getYawAngle())

        self.depthTarget = Target(movable=False)
        mod.getDepthView().addItem(self.depthTarget)
        self.depthTarget.setVisible(False)

        self.depthArrow = pg.ArrowItem(angle=-dev.pitch * 180 / np.pi)
        mod.getDepthView().addItem(self.depthArrow)

        self.ui.setOrientationBtn.toggled.connect(self.setOrientationToggled)
        mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        dev.sigGlobalTransformChanged.connect(self.transformChanged)
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
        self.calibrateAxis.setVisible(self.ui.setOrientationBtn.isChecked())

    def selectedSpeed(self):
        return 'fast' if self.ui.fastRadio.isChecked() else 'slow'

    def sceneMouseClicked(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return

        if self.ui.setCenterBtn.isChecked():
            self.ui.setCenterBtn.setChecked(False)
            pos = self.mod().getView().mapSceneToView(ev.scenePos())
            self.calibrateAxis.setPos(pos)

        elif self.ui.setTargetBtn.isChecked():
            self.target.setVisible(True)
            self.depthTarget.setVisible(True)
            self.ui.targetBtn.setEnabled(True)
            self.ui.approachBtn.setEnabled(True)
            self.ui.setTargetBtn.setChecked(False)
            pos = self.mod().getView().mapSceneToView(ev.scenePos())
            z = self.getDevice().scopeDevice().getFocusDepth()
            self.setTargetPos(pos, z)

    def setTargetPos(self, pos, z=None):
        self.target.setPos(pos)
        if z is None:
            z = self._targetPos[2]
        self.depthTarget.setPos(0, z)
        self._targetPos = (pos.x(), pos.y(), z)

    def targetDragged(self):
        z = self.getDevice().scopeDevice().getFocusDepth()
        self.setTargetPos(self.target.pos(), z)

    def transformChanged(self):
        # manipulator's global transform has changed; update the center arrow and orientation axis
        dev = self.getDevice()
        pos = dev.mapToGlobal([0, 0, 0])
        x = dev.mapToGlobal([1, 0, 0])

        p1 = pg.Point(x[:2])
        p2 = pg.Point(pos[:2])
        p3 = pg.Point(1, 0)
        angle = (p1 - p2).angle(p3)
        if angle is None:
            angle = 0

        self.centerArrow.setPos(pos[0], pos[1])
        self.centerArrow.setStyle(angle=180-angle)
        # self.depthLine.setValue(pos[2])
        self.depthArrow.setPos(0, pos[2])

        self.target.setLabelAngle(dev.getYawAngle())

        if self.ui.setOrientationBtn.isChecked():
            return

        with pg.SignalBlock(self.calibrateAxis.sigRegionChangeFinished, self.calibrateAxisChanged):
            self.calibrateAxis.setPos(pos[:2])
            self.calibrateAxis.setAngle(angle)
            ys = self.calibrateAxis.size()[1]

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
        dev.setStageOrientation(angle, size[1] < 0)

        # next set our position offset
        pos = [pos.x(), pos.y(), z]
        gpos = dev.mapFromGlobal(pos)
        tr = dev.deviceTransform()
        tr.translate(*gpos)
        dev.setDeviceTransform(tr)

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
        self.getDevice().goTarget(self._targetPos, self.selectedSpeed())

    def approachClicked(self):
        self.getDevice().goApproach(self._targetPos, self.selectedSpeed())

    def autoCalibrateClicked(self):
        self.getDevice().tracker.autoCalibrate()

    def getRefFramesClicked(self):
        self.getDevice().tracker.takeReferenceFrames()

    def aboveTargetClicked(self):
        if self._targetPos is None:
            raise Exception("No target selected for %s" % self.getDevice().name())
        self.getDevice().goAboveTarget(self._targetPos, self.selectedSpeed())        


class Target(pg.GraphicsObject):
    sigDragged = QtCore.Signal(object)

    def __init__(self, movable=True):
        pg.GraphicsObject.__init__(self)
        self.movable = movable
        self.moving = False
        self.label = None
        self.labelAngle = 0

    def setLabel(self, label):
        self.label = label
        self.update()

    def setLabelAngle(self, angle):
        self.labelAngle = angle
        self.update()

    def boundingRect(self):
        w = self.pixelLength(pg.Point(1, 0))
        if w is None:
            return QtCore.QRectF()
        w *= 25
        h = 25 * self.pixelLength(pg.Point(0, 1))
        r = QtCore.QRectF(-w*2, -h*2, w*4, h*4)
        return r

    def viewTransformChanged(self):
        self.prepareGeometryChange()

    def paint(self, p, *args):
        p.setRenderHint(p.Antialiasing)
        px = self.pixelLength(pg.Point(1, 0))
        py = self.pixelLength(pg.Point(0, 1))
        w = 5 * px
        h = 5 * py
        r = QtCore.QRectF(-w, -h, w*2, h*2)
        p.setPen(pg.mkPen('y'))
        p.setBrush(pg.mkBrush(0, 0, 255, 100))
        p.drawEllipse(r)
        p.drawLine(pg.Point(-w*2, 0), pg.Point(w*2, 0))
        p.drawLine(pg.Point(0, -h*2), pg.Point(0, h*2))

        if self.label is not None:
            angle = self.labelAngle * np.pi / 180.
            pos = p.transform().map(QtCore.QPointF(0, 0)) + 15 * QtCore.QPointF(np.cos(angle), -np.sin(angle))
            p.resetTransform()
            p.drawText(QtCore.QRectF(pos.x()-10, pos.y()-10, 20, 20), QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, self.label)

    def mouseDragEvent(self, ev):
        if not self.movable:
            return
        if ev.button() == QtCore.Qt.LeftButton:
            if ev.isStart():
                self.moving = True
                self.cursorOffset = self.pos() - self.mapToParent(ev.buttonDownPos())
                self.startPosition = self.pos()
            ev.accept()
            
            if not self.moving:
                return
                
            self.setPos(self.cursorOffset + self.mapToParent(ev.pos()))
            if ev.isFinish():
                self.moving = False
                self.sigDragged.emit(self)

    def hoverEvent(self, ev):
        if self.movable:
            ev.acceptDrags(QtCore.Qt.LeftButton)


class Axis(pg.ROI):
    """Used for calibrating pipette position and orientation.
    """
    def __init__(self, pos, angle, inverty):
        arrow = pg.makeArrowPath(headLen=20, tipAngle=30, tailLen=60, tailWidth=2).translated(-84, 0)
        tr = QtGui.QTransform()
        tr.rotate(180)
        self._path = tr.map(arrow)
        tr.rotate(90)
        self._path |= tr.map(arrow)
        self.pxLen = [1, 1]

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
        self.prepareGeometryChange()

    def updateText(self):
        w, h = self._pxLen
        if w is None:
            return
        self.x.setPos(w*100, 0)
        self.y.setPos(0, h*100)

    def boundingRect(self):
        w, h = self._pxLen
        if w is None:
            return QtCore.QRectF()
        w = w * 100
        h = abs(h * 100)
        r = QtCore.QRectF(-w, -h, w*2, h*2)
        return r

    def paint(self, p, *args):
        p.setRenderHint(p.Antialiasing)
        w, h = self._pxLen
        # r = QtCore.QRectF(-w, -h, w*2, h*2)
        p.setPen(pg.mkPen('y'))
        p.setBrush(pg.mkBrush(255, 255, 0, 100))
        # p.drawEllipse(r)
        # p.drawLine(pg.Point(-w*2, 0), pg.Point(w*2, 0))
        # p.drawLine(pg.Point(0, -h*2), pg.Point(0, h*2))
        p.scale(w, h)
        p.drawPath(self._path)


