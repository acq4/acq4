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
            waypoints = [
                (self.mapToGlobal([endPos[0], 0, dz]), 'fast', True),  # force this move to be linear
                (endPosGlobal, 'fast', False),
            ]
            self.movePath(waypoints)
        else:
            dx = -endPos[2] / np.tan(self.pitch)
            waypoints = [
                (self.mapToGlobal([dx, 0, endPos[2]]), 'fast', True),  # force this move to be linear
                (self.mapToGlobal([endPos[0], 0, endPos[2]]), 'fast', False),
                (endPosGlobal, 'fast', False),
            ]
            self.movePath(waypoints)

    def movePath(self, waypoints):
        """Move the electrode tip along a path of waypoints.

        *waypoints* must be a list of tuples::

            [(globalPos1, speed1, linear1), ...]

        """
        for pt, speed, linear in waypoints:
            f = self._moveToGlobal(pt, speed, linear=linear)
            f.wait()
            if f.wasInterrupted():
                raise Exception("Move was interrupted.")

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


class ManipulatorCamModInterface(QtCore.QObject):
    """Implements user interface for manipulator.
    """
    def __init__(self, dev, mod):
        QtCore.QObject.__init__(self)
        self.dev = dev  # microscope device
        self.mod = mod  # camera module

        self.ui = CamModTemplate()
        self.ctrl = QtGui.QWidget()
        self.ui.setupUi(self.ctrl)

        self.calibrateAxis = Axis([0, 0], 0)
        mod.addItem(self.calibrateAxis)
        self.calibrateAxis.setVisible(False)

        self.centerArrow = pg.ArrowItem()
        mod.addItem(self.centerArrow)

        self.depthLine = self.mod.getDepthView().addLine(y=0, markers=[('v', 1, 20)])

        self.ui.setOrientationBtn.toggled.connect(self.setOrientationToggled)
        self.mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.calibrateAxis.sigRegionChangeFinished.connect(self.calibrateAxisChanged)
        self.calibrateAxis.sigRegionChanged.connect(self.calibrateAxisChanging)
        self.ui.homeBtn.clicked.connect(self.homeClicked)

        self.transformChanged()

    def setOrientationToggled(self):
        self.calibrateAxis.setVisible(self.ui.setOrientationBtn.isChecked())

    def sceneMouseClicked(self, ev):
        if ev.button() != QtCore.Qt.LeftButton or not self.ui.setCenterBtn.isChecked():
            return

        self.ui.setCenterBtn.setChecked(False)
        pos = self.mod.getView().mapSceneToView(ev.scenePos())
        self.calibrateAxis.setPos(pos)

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
        print gpos
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




class Target(pg.GraphicsObject):
    def __init__(self):
        pg.GraphicsObject.__init__(self)
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

