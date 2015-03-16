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

        self.calibrateBtn = QtGui.QPushButton("Calibrate position")
        self.calibrateBtn.setCheckable(True)
        self.layout.addWidget(self.calibrateBtn)

        self.calibrateMarker = Marker()
        mod.addItem(self.calibrateMarker)

        self.transformChanged()

        self.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.mod.window().getView().scene().sigMouseClicked.connect(self.sceneMouseClicked)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)

    def calibrateToggled(self):
        self._calibrating = self.calibrateBtn.isChecked()

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


class Marker(pg.GraphicsObject):
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


