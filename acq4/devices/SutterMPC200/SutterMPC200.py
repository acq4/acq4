# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from ..Stage import Stage
from acq4.drivers.SutterMPC200 import SutterMPC200 as MPC200_Driver
from acq4.util.Mutex import Mutex
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
		self.dev = MPC200_Driver.getDevice(self.port)
		self._notifier.sigPosChanged.connect(self.mpc200PosChanged)

		Stage.__init__(self, man, config, name)

		self.getPosition(refresh=True)

		## May have multiple SutterMPC200 instances (one per drive), but 
		## we only need one monitor.
		if self._monitor is None:
			self._monitor = MonitorThread(self)
			self._monitor.start()

	def checkPositionChange(self, drive=None, pos=None):
		## Anyone may call this function; if any drive has changed position, 
		## SutterMPC200_notifier will emit a signal, and the correct devices will be notified.
		if drive is None:
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
		Stage.quit(self)




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
		minInterval = 100e-6
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
				debug.printExc('Error in MPC200 monirot thread:')
				time.sleep(maxInterval)