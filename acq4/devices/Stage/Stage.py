# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from acq4.devices.OptomechDevice import *
from acq4.util.Mutex import Mutex
import acq4.pyqtgraph as pg

class Stage(Device, OptomechDevice):
    """Base class for mechanical stages with motorized control and/or position feedback.
    """

    sigPositionChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.pos = [0]*3
        
        # self.scale = config.get('scale', None) ## Allow config to apply extra scale factor
        
        dm.declareInterface(name, ['stage'], self)

    def quit(self):
        pass

    def posChanged(self, pos):
        """Handle device position changes by updating the device transform and
        emitting sigPositionChanged.

        Subclasses must call this method when the device position has changed.
        """
        with self.lock:
            rel = [0] * len(self.pos)
            rel[:len(pos)] = [pos[i] - self.pos[i] for i in range(len(pos))]
            self.pos[:len(pos)] = pos
        
        tr = pg.SRTTransform3D()
        tr.translate(*self.pos)
        self.setDeviceTransform(tr) ## this informs rigidly-connected devices that they have moved

        self.sigPositionChanged.emit({'rel': rel, 'abs': self.pos[:]})

    def getPosition(self, refresh=False):
        """
        Return the position of the stage.
        If refresh==False, the last known position is returned. Otherwise, the current position is requested from the controller.
        """
        if not refresh:
            return self.pos[:]
        else:
            return self._getPosition()

    def _getPosition(self):
        """
        Must be reimplemented by subclass to re-read position from device.
        """
        raise NotImplementedError()

    def getState(self):
        with self.lock:
            return (self.pos[:],)

    def deviceInterface(self, win):
        return StageInterface(self, win)

    def moveBy(self, pos, speed, block=True, timeout = 10.):
        """Move by the specified amounts. 
        pos must be a sequence (dx, dy, dz) with values in meters.
        speed will be set before moving unless speed=None
        """
        raise NotImplementedError()

    def moveTo(self, pos, speed, block=True, timeout = 10.):
        """Move by the absolute position. 
        pos must be a sequence (dx, dy, dz) with values in meters.
        speed will be set before moving unless speed=None
        """
        raise NotImplementedError()


class StageInterface(QtGui.QWidget):
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.axLabels = []
        self.posLabels = []
        for axis in [0, 1, 2]:
            axLabel = QtGui.QLabel('XYZ'[axis])
            posLabel = QtGui.QLabel('0')
            self.layout.addWidget(axLabel, axis, 0)
            self.layout.addWidget(posLabel, axis, 1)
            self.axLabels.append(axLabel)
            self.posLabels.append(posLabel)

        self.win = win
        self.dev = dev
        self.dev.sigPositionChanged.connect(self.update)
        self.update()
        

    def update(self):
        pos = self.dev.getPosition()
        for i in range(3):
            text = pg.siFormat(pos[i], suffix='m', precision=5)
            self.posLabels[i].setText(text)

