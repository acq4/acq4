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
        self._defaultSpeed = 'fast'
        
        dm.declareInterface(name, ['stage'], self)

    def quit(self):
        self.stop()
    
    def capabilities(self):
        """Return a structure describing the capabilities of this device::
        
            {
                'getPos': (x, y, z),   # whether eaxh axis can be read from the device
                'setPos': (x, y, z),   # whether eaxh axis can be set on the device
            }
            
        Subclasses must reimplement this method.
        """
        # todo: add other capability flags like resolution, speed, closed-loop, etc?
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
        then the position request may block if the device is currently busy.
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

    def setDefaultSpeed(self, speed):
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
        if speed is None:
            speed = self._defaultSpeed
        if speed is None:
            raise TypeError("Must specify speed or set default speed before moving.")
        if abs is None and rel is None:
            raise TypeError("Must specify one of abs or rel arguments.")
        return self._move(abs, rel, speed)
        
    def _move(self, abs, rel, speed):
        """Must be reimplemented by subclasses and return a MoveFuture instance.
        """
        raise NotImplementedError()

    def _toAbsolutePosition(self, abs, rel):
        """Helper function to convert absolute or relative position (possibly 
        containing Nones) to an absolute position.
        """
        if rel is None:
            if any([x is None for x in abs]):
                pos = self.getPosition()
                for i,x in enumerate(abs):
                    if x is not None:
                        pos[i] = x
        else:
            pos = self.getPosition()
            for i,x in enumerate(rel):
                if x is not None:
                    pos[i] += x
        return pos
        
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
    def __init__(self, dev, pos, speed):
        self.dev = dev
        self.speed = speed
        self.targetPos = pos
        self.startPos = dev.getPosition()
        
    def percentDone(self):
        """Return the percent of the move that has completed.
        
        The default implementation calls getPosition on the device to determine
        the percent complete. Devices that do not provide position updates while 
        moving should reimplement this method.
        """
        s = np.array(self.startPos)
        t = np.array(self.targetPos)
        p = np.array(self.dev.getPosition())
        return 100 * ((p - s) / (t - s)).mean()

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

