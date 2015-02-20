# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from ..Stage import Stage
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
        self.dev = MFC1_Driver(self.port)
        man.sigAbortAll.connect(self.dev.stop)

        self._lastPos = None

        Stage.__init__(self, man, config, name)

        self.getPosition(refresh=True)

        self._monitor = MonitorThread(self)
        self._monitor.start()


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
        self.dev.move(pos[2] / self.scale[2])

    def quit(self):
        self._monitor.stop()
        Stage.quit(self)


class MonitorThread(Thread):
    def __init__(self, dev):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self.stopped = False
        self.interval = 0.1
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
        minInterval = 10e-3
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
