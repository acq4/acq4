# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

import acq4.pyqtgraph as pg
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice


class Manipulator(Device, OptomechDevice):
    """Represents a manipulator controlling an electrode.

    This device provides a camera module interface for driving a motorized electrode holder:

    * Visually direct electrode via camera module
    * Automatically align electrode for diagonal approach to cells

    This device must be configured with a Stage as its parent.
    """
    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)
    
    def quit(self):
        pass
    
    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return None
        
    def cameraModuleInterface(self, mod):
        return ManipulatorCamModInterface(self, mod)


class ManipulatorCamModInterface(QtCore.QObject):
    """Implements user interface for manipulator.
    """
    def __init__(self, dev, mod):
        QtCore.QObject.__init__(self)
        self.dev = dev  # microscope device
        self.mod = mod  # camera module

        self._calibrating = False

        self.ctrl = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.ctrl.setLayout(self.layout)

        self.calibrateBtn = QtGui.QPushButton("Calibrate manipulator")
        self.calibrateBtn.setCheckable(True)
        self.layout.addWidget(self.calibrateBtn)

        self.calibrateAxis = Axis([0, 0], 0)
        mod.addItem(self.calibrateAxis)

        self.transformChanged()

        self.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.calibrateAxis.sigRegionChangeFinished.connect(self.calibrateAxisChanged)

    def calibrateToggled(self):
        # self._calibrating = self.calibrateBtn.isChecked()
        self.axisMarker.setVisible(self.calibrateBtn.isChecked())

    def sceneMouseClicked(self, ev):
        if not self._calibrating:
            return

        self.calibrateBtn.setChecked(False)

    def transformChanged(self):
        pos = self.dev.mapToGlobal([0, 0, 0])
        self.calibrateMarker.setPos(pos[0], pos[1])

    def controlWidget(self):
        return self.ctrl

    def boundingRect(self):
        return None

    def quit(self):
        pass


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

