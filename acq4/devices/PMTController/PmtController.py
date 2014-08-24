# -*- coding: utf-8 -*-
"""
Device interface to PMT Controller.
Polls the PMT settings periodically

"""
from PyQt4 import QtGui, QtCore
from acq4.util.Mutex import Mutex
from acq4.pyqtgraph import debug
from acq4.drivers.PMTController import *
from acq4.drivers.PMTController import PMTController as PMTDriver  ## name collision with device class
import time

try:
    from ..SerialDevice import SerialDevice, TimeoutError, DataError
except ValueError:
    ## relative imports not allowed when running from command prompt
    if __name__ == '__main__':
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from SerialDevice import SerialDevice, TimeoutError, DataError

def threadsafe(method):
    # decorator for automatic mutex lock/unlock
    def lockMutex(self, *args, **kwds):
        with self.lock:
            return method(self, *args, **kwds)
    return lockMutex

class ChangeNotifier(QtCore.QObject):
    """
    Class to emit a signal when we detect that a PMT has tripped it's over-current protection
    """
    sigPmtTripped = QtCore.Signal(object, object, object)


class PmtController(object):
    """
    This Device class represents the PMT controller, an arduino implementation that
    reports PMT currents, command voltages, over current protections,
    and the ability to reset the HV if it has been tripped by high currents..
    Config options are:

        port: <serial port>  # eg. 'COM1' or '/dev/ttyACM0' - the port that talks to the Arduino
        pmts: <pmt>       # an identifier for the PMT (e.g., H7422P-40, H10721-20)
    """

    _notifier = ChangeNotifier()
    _monitor = None

    def __init__(self, man, config, name):
        self.port = config.pop('port')
        self.pmts = config.pop('pmts')  # the type for this PMT
        self.dev = PMTController.getDevice(self.port)
        SerialDevice.__init__(self, port=self.port, baudrate=115200)
        self._notifier.sigPmtTripped.connect(self.pmtTripped)

        ## May have multiple PMT instances (one per PMT), but
        ## we only need one monitor.
        if self._monitor is None:
            self._monitor = MonitorThread(self)
            self._monitor.start()

    def checkPMTCurrent(self, pmt=None):
        ## Anyone may call this function to retrieve the PMT current setting
        ## SutterMPC200_notifier will emit a signal, and the correct devices will be notified.
        if pmt is None:
            pmt = self.dev.getPmt()  # just get the current pmt

                return False

   def checkPMTVoltage(self, pmt=None):
        ## Anyone may call this function to retrieve the PMT anode voltage command
        ## SutterMPC200_notifier will emit a signal, and the correct devices will be notified.
        if pmt is None:
            drive, pos = self.dev.getPos()
        if pos != self._pos_cache[drive]:
            oldpos = self._pos_cache[drive]
            self._notifier.sigPosChanged.emit(drive, pos, oldpos)
            self._pos_cache[drive] = pos
            return (drive, pos, oldpos)
        return False

    def mpc200PosChanged(self, drive, pos, oldpos):
        ## drive has moved; if it is THIS drive, then handle the position change.
        if drive != self.drive:
            return
        self.posChanged(pos)

    def _getPosition(self):
        drive, pos = self.dev.getPos(drive=self.drive)
        self.checkPositionChange(drive, pos) # might as well check while we're here..
        return pos

    def quit(self):
        self._monitor.stop()


class MonitorThread(QtCore.QThread):
    def __init__(self, dev):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self.stopped = False
        self.interval = 0.1
        QtCore.QThread.__init__(self)

    def start(self):
        self.stopped = False
        QtCore.QThread.start(self)

    def stop(self):
        with self.lock:
            self.stopped = True

    def setInterval(self, i):
        with self.lock:
            self.interval = i

    def run(self):
        minInterval = 10e-3  # once per 10 milliseconds; hardware trips faster.
        interval = minInterval
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    maxInterval = self.interval

                if self.dev.checkPositionChange() is not False:
                    interval = minInterval
                else:
                    interval = min(maxInterval, interval*2)

                time.sleep(interval)
            except:
                debug.printExc('Error in PMTController monitor thread:')
                time.sleep(maxInterval)
