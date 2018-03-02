# -*- coding: utf-8 -*-
from __future__ import print_function
import time
from acq4.util import Qt
from ..Stage import Stage, MoveFuture
from acq4.drivers.SutterMPC200 import SutterMPC200 as MPC200_Driver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug, ptime


def __reload__(old):
    # copy some globals if the module is reloaded
    SutterMPC200._monitor = old['SutterMPC200']._monitor


class ChangeNotifier(Qt.QObject):
    """Used to send raw (unscaled) stage position updates to other devices. 
    In particular, focus motors may use this to hijack unused ROE axes.
    """
    sigPosChanged = Qt.Signal(object, object, object)


class SutterMPC200(Stage):
    """
    This Device class represents a single drive of a Sutter MPC-200 stage/manipulator driver.
    Config options are: 

        port: <serial port>  # eg. 'COM1' or '/dev/ttyACM0'
        drive: <drive>       # int 1-4
    """

    _pos_cache = [None] * 4
    _notifier = ChangeNotifier()
    _monitor = None
    _drives = [None] * 4
    slowSpeed = 4  # speed to move when user requests 'slow' movement

    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.drive = config.pop('drive')
        self.scale = config.pop('scale', (1, 1, 1))
        if self._drives[self.drive-1] is not None:
            raise RuntimeError("Already created MPC200 device for drive %d!" % self.drive)
        self._drives[self.drive-1] = self
        self.dev = MPC200_Driver.getDevice(self.port)
        # self._notifier.sigPosChanged.connect(self._mpc200PosChanged)
        man.sigAbortAll.connect(self.stop)

        self._lastMove = None

        Stage.__init__(self, man, config, name)

        # clear cached position for this device and re-read to generate an initial position update
        self._pos_cache[self.drive-1] = None
        self.getPosition(refresh=True)

        ## May have multiple SutterMPC200 instances (one per drive), but 
        ## we only need one monitor.
        if SutterMPC200._monitor is None:
            SutterMPC200._monitor = MonitorThread(self)
            SutterMPC200._monitor.start()

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if 'capabilities' in self.config:
            return self.config['capabilities']
        else:
            return {
                'getPos': (True, True, True),
                'setPos': (True, True, True),
                'limits': (False, False, False),
            }

    def stop(self):
        """Stop _any_ moving drives on the MPC200.
        """
        self.dev.stop()

    @classmethod
    def _checkPositionChange(cls, drive=None, pos=None):
        ## Anyone may call this function. 
        ## If any drive has changed position, SutterMPC200_notifier will emit 
        ## a signal, and the correct devices will be notified.
        if drive is None:
            for dev in cls._drives:
                if dev is None:
                    continue
                drive, pos = dev.dev.getPos()
                break
        if drive is None:
            raise Exception("No MPC200 devices initialized yet.")
        if pos != cls._pos_cache[drive-1]:
            oldpos = cls._pos_cache[drive-1]
            cls._notifier.sigPosChanged.emit(drive, pos, oldpos)
            dev = cls._drives[drive-1]
            if dev is None:
                return False
            cls._pos_cache[drive-1] = pos
            pos = [pos[i] * dev.scale[i] for i in (0, 1, 2)]
            dev.posChanged(pos)

            return (drive, pos, oldpos)
        return False

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        drive, pos = self.dev.getPos(drive=self.drive)
        self._checkPositionChange(drive, pos) # might as well check while we're here..
        pos = [pos[i] * self.scale[i] for i in (0, 1, 2)]
        return pos

    def targetPosition(self):
        if self._lastMove is None or self._lastMove.isDone():
            return self.getPosition()
        else:
            return self._lastMove.targetPos

    def quit(self):
        self._monitor.stop()
        Stage.quit(self)

    def _move(self, abs, rel, speed, linear):
        # convert relative to absolute position, fill in Nones with current position.
        pos = self._toAbsolutePosition(abs, rel)

        # convert speed to values accepted by MPC200
        if speed == 'slow':
            speed = self.slowSpeed
        elif speed == 'fast':
            if linear is True:
                speed = 15
            else:
                speed = 'fast'
        else:
            speed = self._getClosestSpeed(speed)
        
        self._lastMove = MPC200MoveFuture(self, pos, speed)
        return self._lastMove

    def _getClosestSpeed(self, speed):
        """Return the MPC200 speed value (0-15 or 'fast') that most closely
        matches the requested *speed* in m/s.
        """
        speed = float(speed)
        minDiff = None
        bestKey = None
        for k,v in self.dev.speedTable.items():
            diff = abs(speed - v)
            if minDiff is None or diff < minDiff:
                minDiff = diff
                bestKey = k

        return bestKey


class MonitorThread(Thread):
    def __init__(self, dev):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self.stopped = False
        self.interval = 0.3
        
        self.nextMoveId = 0
        self.moveRequest = None
        self._moveStatus = {}
        
        Thread.__init__(self)

    def start(self):
        self.stopped = False
        Thread.start(self)

    def stop(self):
        with self.lock:
            self.stopped = True

    def setInterval(self, i):
        with self.lock:
            self.interval = i
            
    def move(self, drive, pos, speed):
        """Instruct a drive to move. 

        Return an ID that can be used to check on the status of the move until it is complete.
        """
        with self.lock:
            if self.moveRequest is not None:
                raise RuntimeError("Stage is already moving.")
            id = self.nextMoveId
            self.nextMoveId += 1
            self.moveRequest = (id, drive, pos, speed)
            self._moveStatus[id] = (None, None)
            
        return id

    def moveStatus(self, id):
        """Check on the status of a previously requested move.

        Return:
        * None if the request has not been handled yet
        * (start_time, False) if the device is still moving
        * (start_time, True) if the device has stopped
        * (start_time, Exception) instance if there was an error during the move

        If True or an Exception is returned, then the status may not be requested again for the same ID.
        """
        with self.lock:
            start, stat = self._moveStatus[id]
            if stat not in (False, None):
                del self._moveStatus[id]
            return start, stat

    def run(self):
        minInterval = 100e-3
        interval = minInterval
        
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    maxInterval = self.interval
                    moveRequest = self.moveRequest
                    self.moveRequest = None

                if moveRequest is None:
                    # just check for position update
                    if self.dev._checkPositionChange() is not False:
                        interval = minInterval
                    else:
                        interval = min(maxInterval, interval*2)
                else:
                    # move the drive
                    mid, drive, pos, speed = moveRequest
                    try:
                        with self.dev.dev.lock:
                            # record the move starting time only after locking the device
                            start = ptime.time()
                            with self.lock:
                                self._moveStatus[mid] = (start, False)
                            pos = self.dev.dev.moveTo(drive, pos, speed)
                            self.dev._checkPositionChange(drive, pos)
                    except Exception as err:
                        debug.printExc('Move error:')
                        try:
                            if hasattr(err, 'lastPosition'):
                                self.dev._checkPositionChange(drive, err.lastPosition)
                        finally:
                            with self.lock:
                                self._moveStatus[mid] = (start, err)
                    else:
                        with self.lock:
                            self._moveStatus[mid] = (start, True)

                time.sleep(interval)
            except:
                debug.printExc('Error in MPC200 monitor thread:')
                time.sleep(maxInterval)
                

class MPC200MoveFuture(MoveFuture):
    """Provides access to a move-in-progress on an MPC200 drive.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        
        # because of MPC200 idiosyncracies, we must coordinate with the monitor
        # thread to do a move.
        self._expectedDuration = dev.dev.expectedMoveDuration(dev.drive, pos, speed)
        scaled = []
        for i in range(3):
            if dev.scale[i] != 0:
                scaled.append(pos[i] / dev.scale[i])
            else:
                scaled.append(None)
        self._id = SutterMPC200._monitor.move(dev.drive, scaled, speed)
        self._moveStatus = (None, None)
        while True:
            start, status = self._getStatus()
            # block here until move begins (to check for errors in the move call)
            if status is not None:
                break
            time.sleep(5e-3)
        if isinstance(status, Exception):
            raise status
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return isinstance(self._getStatus()[1], Exception)

    def percentDone(self):
        """Return an estimate of the percent of move completed based on the 
        device's speed table.
        """
        if self.isDone():
            return 100
        dt = ptime.time() - self._getStatus()[0]
        if self._expectedDuration == 0:
            return 99
        return max(min(100 * dt / self._expectedDuration, 99), 0)
    
    def isDone(self):
        """Return True if the move is complete.
        """
        return self._getStatus()[1] not in (None, False)

    def _getStatus(self):
        # check status of move unless we already know it is complete.
        if self._moveStatus[1] in (None, False):
            self._moveStatus = SutterMPC200._monitor.moveStatus(self._id)
        return self._moveStatus
        