# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from ..Stage import Stage, StageInterface, MoveFuture
from acq4.drivers.ThorlabsMFC1 import MFC1 as MFC1_Driver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug
import time

class ChangeNotifier(Qt.QObject):
    sigPosChanged = Qt.Signal(object, object, object)


class ThorlabsMFC1(Stage):
    """Thorlabs motorized focus controller (MFC1)
    """

    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.scale = config.pop('scale', (1, 1, 1))
        params = config.pop('motorParams', {})
        self.dev = MFC1_Driver(self.port, **params)
        man.sigAbortAll.connect(self.dev.stop)

        # Optionally use ROE-200 z axis to control focus
        roe = config.pop('roe', None)
        self._roeDev = None
        self._roeEnabled = "waiting"  # ROE control is disabled until after the first update
        if roe is not None:
            dev = man.getDevice(roe)
            self._roeDev = dev
            # need to connect to internal change signal because 
            # the public signal should already have z-axis information removed.
            dev._notifier.sigPosChanged.connect(self._roeChanged)

        self._lastPos = None

        Stage.__init__(self, man, config, name)

        self.getPosition(refresh=True)

        # Optionally read limits from config
        limits = list(config.pop('limits', (None, None)))
        self.setLimits(z=limits)

        self._monitor = MonitorThread(self)
        self._monitor.start()
        
    def capabilities(self):
        # device only reads/writes z-axis
        return {
            'getPos': (False, False, True),
            'setPos': (False, False, True),
            'limits': (False, False, True),
        }

    def mfcPosChanged(self, pos, oldpos):
        self.posChanged(pos)

    def _getPosition(self):
        pos = self.dev.position() * self.scale[2]
        if pos != self._lastPos:
            oldpos = self._lastPos
            self._lastPos = pos
            self.posChanged([0, 0, pos])
        return [0, 0, pos]

    def _move(self, abs, rel, speed, linear):
        # convert relative to absolute position, fill in Nones with current position.
        pos = self._toAbsolutePosition(abs, rel)
        limits = self.getLimits()[2]
        if limits[0] is not None:
            pos[2] = max(pos[2], limits[0])
        if limits[1] is not None:
            pos[2] = min(pos[2], limits[1])
        return MFC1MoveFuture(self, pos, speed)

    def targetPosition(self):
        return [0, 0, self.dev.target_position() * self.scale[2]]

    def quit(self):
        self._monitor.stop()
        Stage.quit(self)

    def _roeChanged(self, drive, pos, oldpos):
        if drive != self._roeDev.drive:
            return
        if self._roeEnabled is not True:
            if self._roeEnabled == 'waiting':
                self._roeEnabled = True
            return
        dz = pos[2] - oldpos[2]
        if dz == 0:
            return
        target = self.dev.target_position() * self.scale[2] + dz
        self.moveTo([0, 0, target], 'fast')

    def deviceInterface(self, win):
        return MFC1StageInterface(self, win)

    def setRoeEnabled(self, enable):
        self._roeEnabled = enable

    def setZero(self):
        """Reset the device position to 0 (without moving the motor).
        """
        self.dev.set_encoder(0)
        self._getPosition()

    def stop(self):
        self.dev.stop()

    def setHolding(self, hold):
        self.dev.set_holding(hold)


class MonitorThread(Thread):
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
                pos = self.dev._getPosition()[2]
                if pos != lastPos:
                    # stage is moving; request more frequent updates
                    interval = minInterval
                else:
                    interval = min(maxInterval, interval*2)
                lastPos = pos

                time.sleep(interval)
            except:
                debug.printExc('Error in MFC1 monitor thread:')
                time.sleep(maxInterval)


class MFC1StageInterface(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)
        if dev._roeDev is not None:
            self.connectRoeBtn = Qt.QPushButton('Enable ROE')
            self.connectRoeBtn.setCheckable(True)
            self.connectRoeBtn.setChecked(True)
            self.layout.addWidget(self.connectRoeBtn, self.nextRow, 0, 1, 2)
            self.connectRoeBtn.toggled.connect(self.connectRoeToggled)

            self.setZeroBtn = Qt.QPushButton('Set Zero')
            self.layout.addWidget(self.setZeroBtn, self.nextRow, 2, 1, 1)
            self.setZeroBtn.clicked.connect(self.setZeroClicked)

    def setZeroClicked(self):
        self.dev.setZero()

    def connectRoeToggled(self, b):
        self.dev.setRoeEnabled(b)


class MFC1MoveFuture(MoveFuture):
    """Provides access to a move-in-progress on an MPC200 drive.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self.startPos = dev.getPosition()
        self.stopPos = pos
        self._moveStatus = {'status': None}
        self.id = dev.dev.move(pos[2] / dev.scale[2])

    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._getStatus()['status'] in ('interrupted', 'failed')

    def percentDone(self):
        """Return an estimate of the percent of move completed based on the 
        device's speed table.
        """
        if self.isDone():
            return 100

        pos = self.dev.getPosition()[2] - self.startPos[2]
        target = self.stopPos[2] - self.startPos[2]
        if target == 0:
            return 99
        return 100 * pos / target

    def isDone(self):
        """Return True if the move is complete.
        """
        return self._getStatus()['status'] in ('interrupted', 'failed', 'done')

    def errorMessage(self):
        stat = self._getStatus()
        if stat['status'] == 'interrupted':
            return "move was interrupted"
        elif stat['status'] == 'failed':
            return "did not reach the expected position (%s != %s)" % (stat['final_pos'], stat['target'])
        else:
            return None

    def _getStatus(self):
        # check status of move unless we already know it is complete.
        if self._moveStatus['status'] in (None, 'moving'):
            self._moveStatus = self.dev.dev.move_status(self.id)
        return self._moveStatus
        


