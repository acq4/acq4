# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import numpy as np

import acq4.pyqtgraph as pg
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from .cameraModTemplate import Ui_Form as CamModTemplate

"""
Todo:

- movement planning:
    - only move diagonally when within 50um of surface
    - limited movement on x/z plane when near objective / recording chamber
- home button
- standby / target buttons
- custom setpoint?
- automatic find: 
    - focus up 500um
    - bring electrode to pre-set location
    - advance slowly along diagonal until tip is detected
    - auto set center
    - move electrode to standby position
    - back to original focus

- show/hide markers
- set center button text should change to "click electrode tip" during setting
- better error reporting when moves are interrupted

"""




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
    """
    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
        self._scopeDev = deviceManager.getDevice(config['scopeDevice'])
        self.pitch = config['pitch'] * np.pi / 180.
        assert isinstance(self.parentDevice(), Stage)

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
        self.writeConfigFile(cal, 'calibration')

    def setDeviceTransform(self, tr):
        OptomechDevice.setDeviceTransform(self, tr)

        cal = self.readConfigFile('calibration')
        cal['transform'] = pg.SRTTransform3D(tr)
        self.writeConfigFile(cal, 'calibration')

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
            self._moveToGlobal(waypoint, speed, linear=True).wait(updates=True)
            self._moveToGlobal(endPosGlobal, speed).wait(updates=True)
        else:
            dx = -endPos[2] / np.tan(self.pitch)
            waypoint1 = self.mapToGlobal([dx, 0, endPos[2]])
            waypoint2 = self.mapToGlobal([endPos[0], 0, endPos[2]])
            self._moveToGlobal(waypoint1, speed, linear=True).wait(updates=True)
            self._moveToGlobal(waypoint2, speed).wait(updates=True)
            self._moveToGlobal(endPosGlobal, speed).wait(updates=True)

    def goStandby(self, target, speed):
        """Move the electrode tip such that it is 100um above the sample surface with its
        axis aligned to the target. 
        """
        stbyDepth = self.standbyDepth()
        pos = self.globalPosition()

        # first retract electrode to standby depth if needed
        if pos[2] < stbyDepth:
            self.advance(stbyDepth, 'slow').wait(updates=True)

        # find axial intersection with current depth plane
        pos = self.globalPosition()
        dz = pos[2] - target[2]
        dx = -dz / np.tan(self.pitch)
        localTarget = self.mapFromGlobal(target)
        stbyPos = np.asarray(localTarget) + np.array([dx, 0, dz])
        # move to target axis
        self._moveToLocal(stbyPos, 'slow', linear=True).wait(updates=True)

        # advance to standby depth
        self.advance(stbyDepth, 'slow').wait(updates=True)

    def goTarget(self, target, speed):
        self._moveToGlobal(target, speed, linear=True).wait(updates=True)

    def standbyDepth(self):
        """Return the global depth where the electrode should move in standby mode.

        This is defined as the sample surface + 100um.
        """
        scope = self.scopeDevice()
        surface = scope.getSurfaceDepth()
        return surface + 100e-6

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
        print "move global:", spos+dif
        return stage.moveToGlobal(spos + dif, speed, linear=linear)

    def _moveToLocal(self, pos, speed, linear=False):
        """Move the electrode tip directly to the given position in local coordinates.
        This method does _not_ implement any motion planning.
        """
        return self._moveToGlobal(self.mapToGlobal(pos), speed, linear=linear)


class ManipulatorCamModInterface(QtCore.QObject):
    """Implements user interface for manipulator.
    """
    def __init__(self, dev, mod):
        QtCore.QObject.__init__(self)
        self.dev = dev  # microscope device
        self.mod = mod  # camera module
        self._targetPos = None

        self.ui = CamModTemplate()
        self.ctrl = QtGui.QWidget()
        self.ui.setupUi(self.ctrl)

        self.calibrateAxis = Axis([0, 0], 0)
        mod.addItem(self.calibrateAxis)
        self.calibrateAxis.setVisible(False)

        self.centerArrow = pg.ArrowItem()
        mod.addItem(self.centerArrow)

        self.target = Target()
        mod.addItem(self.target)
        self.target.setVisible(False)
        self.depthTarget = Target(movable=False)
        mod.getDepthView().addItem(self.depthTarget)
        self.depthTarget.setVisible(False)

        self.depthLine = self.mod.getDepthView().addLine(y=0, markers=[('v', 1, 20)])

        self.ui.setOrientationBtn.toggled.connect(self.setOrientationToggled)
        self.mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.calibrateAxis.sigRegionChangeFinished.connect(self.calibrateAxisChanged)
        self.calibrateAxis.sigRegionChanged.connect(self.calibrateAxisChanging)
        self.ui.homeBtn.clicked.connect(self.homeClicked)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)
        self.ui.targetBtn.clicked.connect(self.targetClicked)
        self.ui.standbyBtn.clicked.connect(self.standbyClicked)

        self.transformChanged()

    def setOrientationToggled(self):
        self.calibrateAxis.setVisible(self.ui.setOrientationBtn.isChecked())

    def sceneMouseClicked(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return

        if self.ui.setCenterBtn.isChecked():
            self.ui.setCenterBtn.setChecked(False)
            pos = self.mod.getView().mapSceneToView(ev.scenePos())
            self.calibrateAxis.setPos(pos)

        elif self.ui.setTargetBtn.isChecked():
            self.target.setVisible(True)
            self.depthTarget.setVisible(True)
            self.ui.targetBtn.setEnabled(True)
            self.ui.standbyBtn.setEnabled(True)
            self.ui.setTargetBtn.setChecked(False)
            pos = self.mod.getView().mapSceneToView(ev.scenePos())
            self.target.setPos(pos)
            z = self.dev.scopeDevice().getFocusDepth()
            self.depthTarget.setPos(0, z)
            self._targetPos = [pos.x(), pos.y(), z]

    def transformChanged(self):
        pos = self.dev.mapToGlobal([0, 0, 0])
        x = self.dev.mapToGlobal([1, 0, 0])

        p1 = pg.Point(x[:2])
        p2 = pg.Point(pos[:2])
        p3 = pg.Point(1, 0)
        angle = (p1 - p2).angle(p3)
        if angle is None:
            angle = 0

        self.centerArrow.setPos(pos[0], pos[1])
        self.centerArrow.setStyle(angle=180-angle)
        self.depthLine.setValue(pos[2])

        if self.ui.setOrientationBtn.isChecked():
            return

        with pg.SignalBlock(self.calibrateAxis.sigRegionChangeFinished, self.calibrateAxisChanged):
            self.calibrateAxis.setPos(pos[:2])
            self.calibrateAxis.setAngle(angle)

    def calibrateAxisChanging(self):
        pos = self.calibrateAxis.pos()
        angle = self.calibrateAxis.angle()

        self.centerArrow.setPos(pos[0], pos[1])
        self.centerArrow.setStyle(angle=180-angle)

    def calibrateAxisChanged(self):
        pos = self.calibrateAxis.pos()
        angle = self.calibrateAxis.angle()
        size = self.calibrateAxis.size()
        z = self.dev.scopeDevice().getFocusDepth()

        # first orient the parent stage
        self.dev.setStageOrientation(angle, size[1] < 0)

        # next set our position offset
        pos = [pos.x(), pos.y(), z]
        gpos = self.dev.mapFromGlobal(pos)
        tr = self.dev.deviceTransform()
        tr.translate(*gpos)
        self.dev.setDeviceTransform(tr)

    def controlWidget(self):
        return self.ctrl

    def boundingRect(self):
        return None

    def quit(self):
        for item in self.calibrateAxis, self.centerArrow, self.depthLine:
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)

    def homeClicked(self):
        self.dev.goHome()

    def setTargetToggled(self, b):
        if b:
            self.ui.setCenterBtn.setChecked(False)

    def setCenterToggled(self, b):
        if b:
            self.ui.setTargetBtn.setChecked(False)

    def targetClicked(self):
        self.dev.goTarget(self._targetPos, 'slow')

    def standbyClicked(self):
        self.dev.goStandby(self._targetPos, 'fast')


class Target(pg.GraphicsObject):
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

    def hoverEvent(self, ev):
        if self.movable:
            ev.acceptDrags(QtCore.Qt.LeftButton)


class Axis(pg.ROI):
    """Used for calibrating manipulator position and orientation.
    """
    def __init__(self, pos, angle):
        arrow = pg.makeArrowPath(headLen=20, tipAngle=30, tailLen=60, tailWidth=2).translated(-84, 0)
        tr = QtGui.QTransform()
        tr.rotate(180)
        self._path = tr.map(arrow)
        tr.rotate(90)
        self._path |= tr.map(arrow)
        self.pxLen = [1, 1]

        pg.ROI.__init__(self, pos, angle=angle, invertible=True, movable=False)
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

