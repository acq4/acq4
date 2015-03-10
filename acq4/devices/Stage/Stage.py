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
    
    def capabilities(self):
        """Return a structure describing the capabilities of this device::
        
            {
                'readPos': (x, y, z),  # whether eaxh axis can be read from the device
                'setPos': (x, y, z),   # whether eaxh axis can be set on the device
            }
            
        Subclasses must reimplement this method.
        """
        raise NotImplementedError
        

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
        If refresh==False, the last known position is returned. Otherwise, the
        current position is requested from the controller. If request is True,
        then the position request may block if the device is currently moving.
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

    def setSpeed(self, speed):
        """Set the default speed of the device when moving.
        
        Generally speeds are specified approximately in m/s, although many 
        devices lack the capability to accurately set speed. This value may 
        also be 'fast' to indicate the device should move as quickly as 
        possible, or 'slow' to indicate the device should minimize vibrations
        while moving.        
        """
        if speed not in ('fast', 'slow'):
            speed = abs(float(speed))
        self._defaultSpeed = speed

    def isMoving(self):
        """Return True if the device is currently moving.
        """
        raise NotImplementedError()        

    def move(self, abs=None, rel=None, speed=None):
        """Move the device to a new position.
        
        Must specify either *abs* for an absolute position, or *rel* for a
        relative position. Either argument must be a sequence (x, y, z) with
        values in meters. Optionally, values may be None to indicate no 
        movement along that axis.
        
        If the *speed* argument is given, it temporarily overrides the default
        speed that was defined by the last call to setSpeed().
        
        Return a MoveFuture instance that can be used to monitor the progress 
        of the move.
        """
        raise NotImplementedError()
        
    def moveBy(self, pos, speed):
        """Move by the specified relative distance. See move() for more 
        information.
        """
        return self.move(rel=pos, speed=speed)

    def moveTo(self, pos, speed, block=True, timeout = 10.):
        """Move to the specified absolute position. See move() for more 
        information.
        """
        return self.move(abs=pos, speed=speed)
    
    def stop(self):
        """Stop moving the device immediately.
        """
        raise NotImplementedError()


class MoveFuture(object):
    """Used to track the progress of a requested move operation.
    """
    def __init__(self, dev):
        self.dev = dev
        
    def percentDone(self):
        """Return the percent of the move that has completed. 
        """
        raise NotImplementedError()

    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        raise NotImplementedError()

    def isDone(self):
        """Return True if the move has completed or was interrupted.
        """
        return self.percentDone() == 100 or self.wasInterrupted()
        
    deef wait(self, timeout=10):
        """Block until the move has completed, been interrupted, or the
        specified timeout has elapsed.
        """
        start = ptime.time()
        while ptime.time() < start+timeout:
            if self.isDone():
                break
            time.sleep(0.1)


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

