# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from ..Stage import Stage
from acq4.drivers.SutterMPC200 import SutterMPC200 as MPC200_Driver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug
import time

class ChangeNotifier(QtCore.QObject):
    sigPosChanged = QtCore.Signal(object, object, object)


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

    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.drive = config.pop('drive')
        self.scale = config.pop('scale', (1, 1, 1))
        self.dev = MPC200_Driver.getDevice(self.port)
        self._notifier.sigPosChanged.connect(self._mpc200PosChanged)
        man.sigAbortAll.connect(self.stop)

        Stage.__init__(self, man, config, name)

        self.getPosition(refresh=True)

        ## May have multiple SutterMPC200 instances (one per drive), but 
        ## we only need one monitor.
        if self._monitor is None:
            self._monitor = MonitorThread(self)
            self._monitor.start()

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if 'capabilities' in self.config:
            return self.config['capabilities']
        else:
            return {
                'getPos': (True, True, True),
                'setPos': (True, True, True),
            }

    def stop(self):
        self.dev.stop(self.drive)

    def _checkPositionChange(self, drive=None, pos=None):
        ## Anyone may call this function. 
        ## If any drive has changed position, SutterMPC200_notifier will emit 
        ## a signal, and the correct devices will be notified.
        if drive is None:
            drive, pos = self.dev.getPos()
        if pos != self._pos_cache[drive]:
            oldpos = self._pos_cache[drive]
            self._notifier.sigPosChanged.emit(drive, pos, oldpos)
            self._pos_cache[drive] = pos
            return (drive, pos, oldpos)
        return False

    def _mpc200PosChanged(self, drive, pos, oldpos):
        ## monitor thread reports that a drive has moved; 
        ## if it is THIS drive, then handle the position change.
        if drive != self.drive:
            return
        pos = [pos[i] * self.scale[i] for i in (0, 1, 2)]
        self.posChanged(pos)

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        drive, pos = self.dev.getPos(drive=self.drive)
        self._checkPositionChange(drive, pos) # might as well check while we're here..
        pos = [pos[i] * self.scale[i] for i in (0, 1, 2)]
        return pos

    def quit(self):
        self._monitor.stop()
        Stage.quit(self)

    def _move(self, abs, rel, speed):
        # convert relative to absolute position, fill in Nones with current position.
        pos = self._toAbsolutePosition(abs, rel)
        
        return MPC200MoveFuture(self, pos, speed)


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
        with self.lock:
            if self.moveRequest is not None:
                raise RuntimeError("Stage is already moving.")
            id = self.nextMoveId
            self.nextMoveId += 1
            self.moveRequest = (id, drive, pos, speed)
            self._moveStatus[id] = {'interrupted': False, 'done': False}
            # start the move here; the thread will check up on it until it's
            # finished.
            self.dev.dev.move(drive, pos, speed)
            
        return id

    def moveStatus(self, id):
        with self.lock:
            return self._moveStatus[id].copy()

    def run(self):
        minInterval = 100e-3
        interval = minInterval
        
        currentMove = None
        
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    maxInterval = self.interval
                    if self.moveRequest is not None:
                        currentMove = self.moveRequest

                if currentMove is None:
                    if self.dev._checkPositionChange() is not False:
                        interval = minInterval
                    else:
                        interval = min(maxInterval, interval*2)
                else:
                    
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
        self._id = SutterMPC200._monitor.move(dev.drive, pos, speed)
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._moveStatus()['interrupted']
    
    def isDone(self):
        """Return True if the move is complete.
        """
        return self._moveStatus()['done']

    def _moveStatus(self):
        return SutterMPC200._monitor.moveStatus(self._id)
        