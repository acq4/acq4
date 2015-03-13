# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from ..Stage import Stage, StageInterface
from acq4.drivers.ThorlabsMFC1 import MFC1 as MFC1_Driver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug
import time

class ChangeNotifier(QtCore.QObject):
    sigPosChanged = QtCore.Signal(object, object, object)


class ThorlabsMFC1(Stage):
    """Thorlabs motorized focus controller (MFC1)
    """

    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.scale = config.pop('scale', (1, 1, 1))
        self.dev = MFC1_Driver(self.port)
        man.sigAbortAll.connect(self.dev.stop)

        # Optionally use ROE-200 z axis to control focus
        roe = config.pop('roe', None)
        self._roeDev = None
        self._roeEnabled = True
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

    def moveBy(self, pos, speed=None):
        cpos = self.getPosition()
        cpos[2] += pos[2]
        self.moveTo(cpos, speed)

    def moveTo(self, pos, speed=None):
        limits = self.getLimits()[2]
        if limits[0] is not None:
            z = max(pos[2], limits[0])
        if limits[1] is not None:
            z = min(pos[2], limits[0])

        self.dev.move(z / self.scale[2])

    def quit(self):
        self._monitor.stop()
        Stage.quit(self)

    def _roeChanged(self, drive, pos, oldpos):
        if self._roeEnabled is not True:
            return
        if drive != self._roeDev.drive:
            return
        dz = pos[2] - oldpos[2]
        if dz == 0:
            return
        target = self.dev.target_position() * self.scale[2] + dz
        self.moveTo([0, 0, target])

    def deviceInterface(self, win):
        return MFC1StageInterface(self, win)

    def setRoeEnabled(self, enable):
        self._roeEnabled = enable

    def setZero(self):
        """Set the device to read z=0 at the current position.
        """
        self.dev.set_encoder(0)
        self._getPosition()


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
            self.connectRoeBtn = QtGui.QPushButton('Enable ROE')
            self.connectRoeBtn.setCheckable(True)
            self.connectRoeBtn.setChecked(True)
            self.layout.addWidget(self.connectRoeBtn, 3, 0, 1, 1)
            self.connectRoeBtn.toggled.connect(self.connectRoeToggled)

            self.setZeroBtn = QtGui.QPushButton('Set Zero')
            self.layout.addWidget(self.setZeroBtn, 4, 0, 1, 1)
            self.setZeroBtn.toggled.connect(self.setZeroClicked)

            self.setUpperBtn = QtGui.QPushButton('Set Upper Limit')
            self.layout.addWidget(self.setUpperBtn, 3, 1, 1, 1)
            self.setUpperBtn.toggled.connect(self.setUpperClicked)

            self.setLowerBtn = QtGui.QPushButton('Set Lower Limit')
            self.layout.addWidget(self.setLowerBtn, 4, 1, 1, 1)
            self.setLowerBtn.toggled.connect(self.setLowerClicked)

    def setZeroClicked(self):
        self.dev.setZero()

    def setUpperClicked(self):
        self.dev.setUpperLimit()

    def setLowerClicked(self):
        self.dev.setLowerLimit()

    def connectRoeToggled(self, b):
        self.dev.setRoeEnabled(b)


