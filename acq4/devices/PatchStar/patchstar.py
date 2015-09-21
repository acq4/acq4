# -*- coding: utf-8 -*-
import time
import numpy as np
from PyQt4 import QtGui, QtCore
from ..Stage import Stage, MoveFuture, StageInterface
from acq4.drivers.PatchStar import PatchStar as PatchStarDriver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug, ptime, SpinBox


class PatchStar(Stage):
    """
    A Scientifica PatchStar manipulator.

        port: <serial port>  # eg. 'COM1' or '/dev/ttyACM0'
    """
    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.scale = config.pop('scale', (1e-7, 1e-7, 1e-7))
        self.dev = PatchStarDriver(self.port)
        self._lastMove = None
        man.sigAbortAll.connect(self.stop)

        Stage.__init__(self, man, config, name)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        self.getPosition(refresh=True)
        self.setUserSpeed(3e-3)

        # Set scaling for each axis
        self.dev.send('UUX 6.4')
        self.dev.send('UUY 6.4')
        self.dev.send('UUZ 6.4')

        # makes 1 roe turn == 1 second movement for any speed
        self.dev.send('JS 200')

        # Set approach angle
        self.dev.send('ANGLE %f' % self.pitch)
        self.dev.send('APPROACH 0')

        # thread for polling position changes
        self.monitor = MonitorThread(self)
        self.monitor.start()

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
        """Stop the manipulator immediately.
        """
        with self.lock:
            self.dev.stop()
            if self._lastMove is not None:
                self._lastMove._stopped()
            self._lastMove = None

    def setUserSpeed(self, v):
        """Set the speed of the rotary controller (m/turn).
        """
        self.userSpeed = v
        self.dev.setSpeed(v / self.scale[0])

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = self.dev.getPos()
            pos = [pos[i] * self.scale[i] for i in (0, 1, 2)]
            if pos != self._lastPos:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def quit(self):
        self.monitor.stop()
        Stage.quit(self)

    def _move(self, abs, rel, speed, linear):
        with self.lock:
            if self._lastMove is not None and not self._lastMove.isDone():
                self.stop()
            pos = self._toAbsolutePosition(abs, rel)
            self._lastMove = PatchStarMoveFuture(self, pos, speed, self.userSpeed)
            return self._lastMove

    def deviceInterface(self, win):
        return PatchStarGUI(self, win)


class MonitorThread(Thread):
    """Thread to poll for manipulator position changes.
    """
    def __init__(self, dev):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self.stopped = False
        self.interval = 0.3
        
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
    
    def run(self):
        minInterval = 100e-3
        interval = minInterval
        lastPos = None
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    maxInterval = self.interval

                pos = self.dev._getPosition()  # this causes sigPositionChanged to be emitted
                if pos != lastPos:
                    # if there was a change, then loop more rapidly for a short time.
                    interval = minInterval
                    lastPos = pos
                else:
                    interval = min(maxInterval, interval*2)

                time.sleep(interval)
            except:
                debug.printExc('Error in PatchStar monitor thread:')
                time.sleep(maxInterval)
                

class PatchStarMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a PatchStar manipulator.
    """
    def __init__(self, dev, pos, speed, userSpeed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMSg = None
        self._finished = False
        pos = (np.array(pos) / np.array(self.dev.scale)).astype(int)
        if speed == 'fast':
            speed = 1e-3
        elif speed == 'slow':
            speed = 1e-6
        with self.dev.dev.lock:
            self.dev.dev.moveTo(pos, speed / self.dev.scale[0])
            # reset to user speed immediately after starting move
            # (the move itself will run with the previous speed)
            self.dev.dev.setSpeed(userSpeed / self.dev.scale[0])
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._interrupted

    def isDone(self):
        """Return True if the move is complete.
        """
        return self._getStatus() != 0

    def _getStatus(self):
        # check status of move unless we already know it is complete.
        # 0: still moving; 1: finished successfully; -1: finished unsuccessfully
        if self._finished:
            if self._interrupted:
                return -1
            else:
                return 1
        if self.dev.dev.isMoving():
            # Still moving
            return 0
        # did we reach target?
        pos = self.dev._getPosition()
        if ((np.array(pos) - np.array(self.targetPos))**2).sum()**0.5 < 1e-6:
            # reached target
            self._finished = True
            return 1
        else:
            # missed
            self._finished = True
            self._interrupted = True
            self._errorMsg = "Move did not complete."
            return -1

    def _stopped(self):
        # Called when the manipulator is stopped, possibly interrupting this move.
        status = self._getStatus()
        if status == 1:
            # finished; ignore stop
            return
        elif status == -1:
            self._errorMsg = "Move was interrupted before completion."
        elif status == 0:
            # not actually stopped! This should not happen.
            raise RuntimeError("Interrupted move but manipulator is still running!")
        else:
            raise Exception("Unknown status: %s" % status)

    def errorMessage(self):
        return self._errorMsg



class PatchStarGUI(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)

        # Insert patchstar-specific controls into GUI
        self.psGroup = QtGui.QGroupBox('PatchStar Rotary Controller')
        self.layout.addWidget(self.psGroup, self.nextRow, 0, 1, 2)
        self.nextRow += 1

        self.psLayout = QtGui.QGridLayout()
        self.psGroup.setLayout(self.psLayout)
        self.speedLabel = QtGui.QLabel('Speed')
        self.speedSpin = SpinBox(value=self.dev.userSpeed, suffix='m/turn', siPrefix=True, dec=True, limits=[1e-6, 10e-3])
        self.revXBtn = QtGui.QPushButton('Reverse X')
        self.revYBtn = QtGui.QPushButton('Reverse Y')
        self.revZBtn = QtGui.QPushButton('Reverse Z')
        self.psLayout.addWidget(self.speedLabel, 0, 0)
        self.psLayout.addWidget(self.speedSpin, 0, 1)
        self.psLayout.addWidget(self.revXBtn, 1, 1)
        self.psLayout.addWidget(self.revYBtn, 2, 1)
        self.psLayout.addWidget(self.revZBtn, 3, 1)

        self.revXBtn.clicked.connect(lambda: self.dev.dev.send('JDX'))
        self.revYBtn.clicked.connect(lambda: self.dev.dev.send('JDY'))
        self.revZBtn.clicked.connect(lambda: self.dev.dev.send('JDZ'))

        self.speedSpin.valueChanged.connect(lambda v: self.dev.setDefaultSpeed(v))

