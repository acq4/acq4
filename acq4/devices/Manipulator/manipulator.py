# -*- coding: utf-8 -*-
from __future__ import division

from PyQt4 import QtCore, QtGui
import numpy as np

from acq4.Manager import getManager
import acq4.pyqtgraph as pg
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from acq4.modules.Camera import CameraModuleInterface
from .cameraModTemplate import Ui_Form as CamModTemplate


class Manipulator(Device, OptomechDevice):
    """Represents a manipulator controlling an electrode.

    This device provides a camera module interface for driving a motorized electrode holder:

    * Visually direct electrode via camera module
    * Automatically align electrode for diagonal approach to cells

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

    * searchHeight: the distance to focus above the sample surface when searching for pipette tips
    * approachHeight: the distance to bring the pipette tip above the sample surface when beginning 
      a diagonal approach
    * idleHeight: the distance to bring the pipette tip above the sample surface when in idle position
    * idleDistance: the distance from the global origin from which the pipette top should be placed
      in idle mode
    """
    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
        self._scopeDev = deviceManager.getDevice(config['scopeDevice'])
        self._stageOrientation = {'angle': 0, 'inverty': False}
        self._opts = {
            'searchHeight': config.get('searchHeight', 2e-3),
            'approachHeight': config.get('approachHeight', 100e-6),
            'idleHeight': config.get('idleHeight', 1e-3),
            'idleDistance': config.get('searchHeight', 7e-3),
        }
        parent = self.parentDevice()
        assert isinstance(parent, Stage)
        self.pitch = parent.pitch * np.pi / 180.

        cal = self.readConfigFile('calibration')
        if cal != {}:
            self.setStageOrientation(cal['angle'], cal['inverty'])
            self.setDeviceTransform(cal['transform'])

    def scopeDevice(self):
        return self._scopeDev

    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None

    def cameraModuleInterface(self, mod):
        return ManipulatorCamModInterface(self, mod)

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
        """Extract pipette tip diagonally, then move manipulator far away from the objective.

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
        searchDepth = scope.getSurfaceDepth() + self._opts['searchHeight']
        if scope.getFocusDepth() < searchDepth:
            scope.setFocusDepth(searchDepth).wait()

        # Here's where we want the pipette tip in global coordinates:
        #   500 um below center of scope focus
        globalTarget = scope.mapToGlobal([0, 0, -500e-6])
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

        # compute approach position
        dz2 = stbyDepth - target[2]
        dx2 = -dz2 / np.tan(self.pitch)
        stby = ltarget + np.array([dx2, 0., dz2])

        # compute intermediate position
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


class ManipulatorCamModInterface(CameraModuleInterface):
    """Implements user interface for manipulator.
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
        self._targetPos = [pos.x(), pos.y(), z]

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


class Target(pg.GraphicsObject):
    sigDragged = QtCore.Signal(object)

    def __init__(self, movable=True):
        pg.GraphicsObject.__init__(self)
        self.movable = movable
        self.moving = False

    def boundingRect(self):
        w = self.pixelLength(pg.Point(1, 0))
        if w is None:
            return QtCore.QRectF()
        w *= 5
        h = 5 * self.pixelLength(pg.Point(0, 1))
        r = QtCore.QRectF(-w*2, -h*2, w*4, h*4)
        return r

    def viewTransformChanged(self):
        self.prepareGeometryChange()

    def paint(self, p, *args):
        p.setRenderHint(p.Antialiasing)
        w = 5 * self.pixelLength(pg.Point(1, 0))
        h = 5 * self.pixelLength(pg.Point(0, 1))
        r = QtCore.QRectF(-w, -h, w*2, h*2)
        p.setPen(pg.mkPen('y'))
        p.setBrush(pg.mkBrush(0, 0, 255, 100))
        p.drawEllipse(r)
        p.drawLine(pg.Point(-w*2, 0), pg.Point(w*2, 0))
        p.drawLine(pg.Point(0, -h*2), pg.Point(0, h*2))

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
    """Used for calibrating manipulator position and orientation.
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


class AccuracyTester(object):
    def __init__(self, manipulator):
        self.dev = manipulator
        man = getManager()
        self.camera = man.getDevice('Camera')
        self.reference = self.dev.readConfigFile('ref_frames')

    def takeFrame(self, padding=40e-6):
        """Acquire one frame from the imaging device.
        """
        restart = False
        if self.camera.isRunning():
            restart = True
            self.camera.stop()
        frame = self.camera.acquireFrames(1)
        if restart:
            self.camera.start()
        return frame

    def getTipImageArea(self, frame, padding):
        """Generate coordinates needed to clip a camera frame to include just the
        tip of the pipette and some padding.

        Return a tuple (minImgPos, maxImgPos, tipRelPos), where the first two
        items are (x,y) coordinate pairs giving the corners of the image region to 
        be extracted, and tipRelPos is the subpixel location of the pipette tip
        within this region.
        """
        img = frame.data()[0]

        # determine bounding rectangle that we would like to acquire from the tip
        tipPos = self.dev.globalPosition()
        tipPos = np.array([tipPos[0], tipPos[1]])
        angle = self.dev.getYawAngle() * np.pi / 180.
        da = 10 * np.pi / 180  # half-angle of the tip
        tipLen = 30e-6  # how far back to image along the tip
        pxw = frame.info()['pixelSize'][0]
        # compute back points of a triangle that circumscribes the tip
        backPos1 = np.array([-tipLen * np.cos(angle+da), -tipLen * np.sin(angle+da)])
        backPos2 = np.array([-tipLen * np.cos(angle-da), -tipLen * np.sin(angle-da)])

        # convert to image coordinates
        tr = frame.globalTransform().inverted()[0]
        originImgPos = tr.map(pg.Vector([0, 0]))
        backImgPos1 = tr.map(pg.Vector(backPos1)) - originImgPos
        backImgPos2 = tr.map(pg.Vector(backPos2)) - originImgPos
        backImgPos1 = np.array([backImgPos1.x(), backImgPos1.y()])
        backImgPos2 = np.array([backImgPos2.x(), backImgPos2.y()])

        # Pixel positions of bounding corners in the image relative to tip, including padding.
        # Note this is all calculated without actual tip position; this ensures the image
        # size is constant even as the tip moves.
        allPos = np.vstack([[0, 0], backImgPos1, backImgPos2]).astype('int')
        padding = int(padding / pxw)
        minRelPos = allPos.min(axis=0) - padding
        maxRelPos = allPos.max(axis=0) + padding

        # Get absolute pixel position of tip within image
        tipImgPos = tr.map(pg.Vector(tipPos))
        tipImgPos = np.array([tipImgPos.x(), tipImgPos.y()])
        tipImgPx = tipImgPos.astype('int')

        # clip bounding coordinates
        minRelPos = [np.clip(minRelPos[0], -tipImgPx[0], img.shape[0]-1-tipImgPx[0]), 
                     np.clip(minRelPos[1], -tipImgPx[1], img.shape[1]-1-tipImgPx[1])]
        maxRelPos = [np.clip(maxRelPos[0], -tipImgPx[0], img.shape[0]-1-tipImgPx[0]), 
                     np.clip(maxRelPos[1], -tipImgPx[1], img.shape[1]-1-tipImgPx[1])]

        # absolute image coordinates of bounding rect
        minImgPos = tipImgPx + minRelPos
        maxImgPos = tipImgPx + maxRelPos

        if np.any(maxImgPos - minImgPos < 1):
            raise RuntimeError("No part of tip overlaps with camera frame.")

        # subpixel location of tip within image
        tipRelPos = tipImgPos - tipImgPx - minRelPos

        return minImgPos, maxImgPos, tipRelPos

    def takeTipImage(self, padding=50e-6):
        """Acquire an image of the pipette tip plus some padding.

        Return a tuple (image, tipPosition).
        """
        frame = self.takeFrame()

        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(frame, padding)

        # clipped image region
        subimg = frame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]

        return subimg, tipRelPos

    def takeReferenceFrames(self, zRange=40e-6, zStep=2e-6):
        """Collect a series of images of the pipette tip at various focal depths.

        The collected images are used as reference templates for determining the most likely location 
        and focal depth of the tip after the calibration is no longer valid.

        The tip is first moved in the +z direction by half of *zRange*, and then stepped in the -z 
        direction by *zStep* until the entire *zRange* is covered. Images of the pipette tip are acquired
        and stored at each step.

        This method assumes that the tip is in focus near the center of the camera frame, and that its
        position is well-calibrated. Ideally, the illumination is flat and the area surrounding the tip
        is free of any artifacts.

        Images are filtered using `self.filterImage` before they are stored.
        """
        # Take an initial frame with the tip in focus.
        centerFrame = self.takeFrame()
        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(centerFrame, padding=5e-6)
        center = centerFrame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]
        center = self.filterImage(center)

        # Decide how many frames to collect and at what z depths
        nFrames = (int(zRange / zStep) // 2) * 2
        pos = self.dev.globalPosition()
        zStart = pos[2] + zStep * (nFrames // 2)
        frames = []
        corr = []

        # Set initial focus above start point to reduce hysteresis in focus mechanism
        scope = self.dev.scopeDevice()
        scope.setFocusDepth(zStart + 10e-6)

        # Stop camera if it is currently running
        restart = False
        if self.camera.isRunning():
            restart = True
            self.camera.stop()

        try:
            with pg.ProgressDialog('Acquiring reference frames...', 0, nFrames) as dlg:
                # Acquire multiple frames at different depths
                for i in range(nFrames):
                    #pos[2] = zStart - zStep * i
                    # self.dev._moveToGlobal(pos, 'slow').wait()
                    scope.setFocusDepth(zStart - zStep * i).wait()
                    frame = self.camera.acquireFrames(1)
                    img = frame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]
                    img = self.filterImage(img)
                    frames.append(img)
                    corr.append(self._matchTemplateSingle(img, center)[1])
                    dlg += 1
                    if dlg.wasCanceled():
                        return
        finally:
            # restart camera if it was running
            if restart:
                self.camera.start()

        # find the index of the frame that most closely matches the initial, tip-focused frame
        maxInd = np.argmax(corr)

        # stack all frames into a 3D array
        frames = np.dstack(frames).transpose((2, 0, 1))

        # generate downsampled frame versions
        # (for now we generate these on the fly..)
        # ds = [frames] + [pg.downsample(pg.downsample(frames, n, axis=1), n, axis=2) for n in [2, 4, 8]]

        self.reference = {
            'frames': frames,
            'zStep': zStep,
            'centerInd': maxInd,
            'centerPos': tipRelPos,
            # 'downsampledFrames' = ds,
        }

        self.dev.writeConfigFile(self.reference, 'ref_frames')

    def measureTipPosition(self, padding=50e-6, threshold=0.7, frame=None):
        """Find the pipette tip location by template matching within a region surrounding the
        expected tip position.

        If the strength of the match is less than *threshold*, then raise RuntimeError.
        """
        if frame is None:
            frame = self.takeFrame()
        minImgPos, maxImgPos, tipRelPos = self.getTipImageArea(frame, padding)
        img = frame.data()[0, minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]
        img = self.filterImage(img)

        match = [self.matchTemplate(img, t) for t in self.reference['frames']]
        maxInd = np.argmax([m[1] for m in match])
        if match[maxInd][1] < threshold:
            raise RuntimeError("Unable to locate pipette tip (correlation %0.2f < %0.2f)" % (match[maxInd][1], threshold))

        zErr = (maxInd - self.reference['centerInd']) * self.reference['zStep']

        offset = match[maxInd][0]
        tipImgPos = (minImgPos[0] + offset[0] + self.reference['centerPos'][0], 
                     minImgPos[1] + offset[1] + self.reference['centerPos'][1])
        tipPos = frame.mapFromFrameToGlobal(pg.Vector(tipImgPos))
        return tipPos.x(), tipPos.y(), tipPos.z() + zErr

    def measureError(self, padding=50e-6, threshold=0.7, frame=None):
        """Return an (x, y, z) tuple indicating the error vector from the calibrated tip position to the
        measured (actual) tip position.
        """
        expectedTipPos = self.dev.globalPosition()
        measuredTipPos = self.measureTipPosition(padding, threshold, frame)
        return tuple([measuredTipPos[i] - expectedTipPos[i] for i in (0, 1, 2)])

    def autoCalibrate(self, padding=50e-6, threshold=0.7):
        """Automatically calibrate the pipette tip position using template matching on a single camera frame.
        """
        tipPos = self.measureTipPosition(padding, threshold)
        localError = self.dev.mapFromGlobal(tipPos)
        tr = self.dev.deviceTransform()
        tr.translate(pg.Vector(localError))
        self.dev.setDeviceTransform(tr)

    def filterImage(self, img):
        """Return a filtered version of an image to be used in template matching.

        Currently, no filtering is applied.
        """
        # Sobel should reduce background artifacts, but it also seems to increase the noise in the signal
        # itself--two images with slightly different focus can have a very bad match.
        # import skimage.feature
        # return skimage.filter.sobel(img)

        return img

    def matchTemplate(self, img, template, dsVals=(8, 1)):
        """Match a template to image data.

        Return the (x, y) pixel offset of the template and a value indicating the strength of the match.

        For efficiency, the input images are downsampled and matched at low resolution before
        iteratively re-matching at higher resolutions. The *dsVals* argument lists the downsampling values
        that will be used, in order. Each value in this list must be an integer multiple of
        the value that follows it.
        """
        # Recursively match at increasing image resolution

        imgDs = [pg.downsample(pg.downsample(img, n, axis=0), n, axis=1) for n in dsVals]
        tmpDs = [pg.downsample(pg.downsample(template, n, axis=0), n, axis=1) for n in dsVals]
        offset = np.array([0, 0])
        for i, ds in enumerate(dsVals):
            pos, val = self._matchTemplateSingle(imgDs[i], tmpDs[i])
            pos = np.array(pos)
            if i == len(dsVals) - 1:
                offset += pos
                # [pg.image(imgDs[j], title=str(j)) for j in range(len(dsVals))]
                return offset, val
            else:
                scale = ds // dsVals[i+1]
                assert scale == ds / dsVals[i+1], "dsVals must satisfy constraint: dsVals[i] == dsVals[i+1] * int(x)"
                offset *= scale
                offset += np.clip(((pos-1) * scale), 0, imgDs[i+1].shape)
                end = offset + np.array(tmpDs[i+1].shape) + 3
                end = np.clip(end, 0, imgDs[i+1].shape)
                imgDs[i+1] = imgDs[i+1][offset[0]:end[0], offset[1]:end[1]]

    def _matchTemplateSingle(self, img, template):
        import skimage.feature
        if img.shape[0] < template.shape[0] or img.shape[1] < template.shape[1]:
            raise ValueError("Image must be larger than template.  %s %s" % (img.shape, template.shape))
        cc = skimage.feature.match_template(img, template)
        ind = np.argmax(cc)
        pos = np.unravel_index(ind, cc.shape)
        val = cc[pos[0], pos[1]]
        return pos, val

    def mapErrors(self, width, step, padding=20e-6, threshold=0.5, show=False):
        start = np.array(self.dev.globalPosition())
        n = int(width/step) + 1
        inds = np.mgrid[0:n, 0:n].reshape((2, n*n)).transpose()
        order = np.arange(n*n)
        np.random.shuffle(order)

        err = np.zeros((n, n, 3))

        # loop over all points in random order, and such that we do heavy computation while
        # pipette is moving.
        images = []
        with pg.ProgressDialog("Acquiring error map...", 0, len(order)) as dlg:
            for i in range(len(order)+1):
                if i > 0:
                    last_pos = pos
                if i < len(order):
                    ind = inds[order[i]]
                    pos = start.copy()
                    pos[:2] += step * ind
                    fut = self.dev._moveToGlobal(pos, 'fast')
                if i > 0:
                    ind = inds[order[i-1]]

                    if show:
                        img = frame.data()[0]
                        p1 = frame.globalTransform().inverted()[0].map(pg.Vector(last_pos))
                        img[p1.x(), p1.y()] += 10000
                        images.append(img)
                        # pg.image(img, title=str(ind) + ' ' + str(p1))

                    err[tuple(ind)] = self.measureError(padding=padding, threshold=threshold, frame=frame)
                    dlg += 1
                fut.wait()
                frame = self.takeFrame()

                if dlg.wasCanceled():
                    return None

        self.dev._moveToGlobal(start, 'fast')


        if show:
            pg.image(np.dstack(images).transpose(2, 0, 1))

        return err

















