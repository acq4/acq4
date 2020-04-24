# -*- coding: utf-8 -*-
from __future__ import print_function
import time
import numpy as np
from acq4.util import Qt
from ..Stage import Stage, MoveFuture, StageInterface
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug, ptime, SpinBox
from acq4.util.micromanager import getMMCorePy


class MicroManagerStage(Stage):
    """
    Class to wrap the micromanager xy stage

    """
    def __init__(self, man, config, name):
        self.scale = config.pop('scale', (1e-6, 1e-6, 1e-6))
        self.speedToMeters = .001
        self.mmc = getMMCorePy()

        self._mmDeviceNames = {'xy': None, 'z': None}
        self._mmSerialPortNames = {'xy': None, 'z': None}
        self._axes = []

        # Configure XY and Z stages separately
        if 'xyStage' not in config and 'zStage' not in config:
            raise Exception("Micromanager stage configuration myst have 'xyStage', 'zStage', or both.")
        allAdapters = self.mmc.getDeviceAdapterNames()
        for axes in ('xy', 'z'):

            # sanity check for MM adapter and device name
            stageCfg = config.get(axes + 'Stage', None)
            if stageCfg is None:
                continue
            self._axes.append(axes)

            adapterName = stageCfg['mmAdapterName']
            if adapterName not in allAdapters:
                raise ValueError("Adapter name '%s' is not valid. Options are: %s" % (adapterName, allAdapters))
            mmDeviceName = stageCfg.get('mmDeviceName', None)
            allDevices = self.mmc.getAvailableDevices(adapterName)
            if mmDeviceName not in allDevices:
                raise ValueError("Device name '%s' is not valid for adapter '%s'. Options are: %s" % (mmDeviceName, adapterName, allDevices))

            # Load this device
            devName = str(name) + '_' + axes
            self._mmDeviceNames[axes] = devName
            self.mmc.loadDevice(devName, adapterName, mmDeviceName)

            # Set up serial port if needed
            if 'serial' in stageCfg:
                # Z stage may use the same serial port as XY stage
                if stageCfg['serial']['port'] == 'shared':
                    if axes != 'z':
                        raise Exception('Shared serial port only allowed for Z axis.')
                    if 'xyStage' not in config:
                        raise Exception('Shared serial port requires xyStage.')
                    portName = self._mmDeviceNames['xy'] + '_port'
                    self.mmc.setProperty(devName, 'Port', portName)
                    self._mmSerialPortNames[axes] = portName
                else:
                    portName = devName + "_port"
                    self.mmc.loadDevice(portName, "SerialManager", str(stageCfg['serial']['port']))
                    if 'baud' in stageCfg['serial']:
                        self.mmc.setProperty(portName, 'BaudRate', stageCfg['serial']['baud'])
                    self.mmc.setProperty(devName, 'Port', portName)
                    self.mmc.initializeDevice(portName)
                    self._mmSerialPortNames[axes] = portName

            self.mmc.initializeDevice(devName)

        self._lastMove = None
        self._focusDevice = self
        # self.userSpeed = np.asarray(self.mmc.getProperty(self._mmDeviceName, 'Speed-S')).astype(float) * self.speedToMeters
        man.sigAbortAll.connect(self.abort)

        Stage.__init__(self, man, config, name)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        time.sleep(1.0)
        self.getPosition(refresh=True)
        
        # thread for polling position changes
        self.monitor = MonitorThread(self)
        self.monitor.start()

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if 'capabilities' in self.config:
            return self.config['capabilities']
        else:
            haveXY = 'xy' in self._axes
            haveZ = 'z' in self._axes
            return {
                'getPos': (haveXY, haveXY, haveZ),
                'setPos': (haveXY, haveXY, haveZ),
                'limits': (False, False, False),
            }

    def stop(self):
        """Stop the manipulator.

        If the manipulator is currently in use elsewhere, this method blocks until it becomes available.
        """
        with self.lock:
            for ax in self._axes:
                self.mmc.stop(self._mmDeviceNames[ax])
                if self._lastMove is not None:
                    self._lastMove._stopped()
                    self._lastMove = None

    def abort(self):
        """Stop the manipulator immediately.

        This method asks the manipulator to stop even if it is being accessed elsewhere.
        This can cause communication errors, but may be preferred if stopping immediately is critical.
        """
        for ax in self._axes:
            try:
                self.mmc.stop(self._mmDeviceNames[ax])
                if self._lastMove is not None:
                    self._lastMove._stopped()
                    self._lastMove = None
            except:
                printExc("Error stopping axis %s:" % ax)

    def setUserSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under manual control.

        The stage's maximum speed is reset to this value when it is not under
        programmed control.
        """
        self.userSpeed = v
        self.mmc.setProperty(self._mmDeviceName, 'Speed-S', v / self.speedToMeters)

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = [0., 0., 0.]
            if 'xy' in self._axes:
                pos[0] = self.mmc.getXPosition(self._mmDeviceNames['xy']) * self.scale[0]
                pos[1] = self.mmc.getYPosition(self._mmDeviceNames['xy']) * self.scale[1]
            if 'z' in self._axes:
                pos[2] = self.mmc.getPosition(self._mmDeviceNames['z']) * self.scale[2]

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

            # Decide which axes to move
            moveXY = True
            if abs is not None:
                moveZ = abs[2] is not None
                moveXY = abs[0] is not None and abs[1] is not None
            else:
                moveZ = rel[2] is not None
                moveXY = rel[0] is not None and rel[1] is not None

            speed = self._interpretSpeed(speed)

            self._lastMove = MicroManagerMoveFuture(self, pos, speed, self.userSpeed, moveXY=moveXY, moveX=moveZ)
            return self._lastMove

    def deviceInterface(self, win):
        return MicroManagerGUI(self, win)

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity.
        """
        raise Exception("MicroManager stage does not support startMoving() function.")



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
                debug.printExc('Error in MicromanagerStage monitor thread:')
                time.sleep(maxInterval)
                

class MicroManagerMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a micromanager stage.
    """
    def __init__(self, dev, pos, speed, userSpeed, moveXY=True, moveZ=True):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMSg = None
        self._finished = False
        pos = np.array(pos) / np.array(self.dev.scale)
        with self.dev.lock:
            if moveXY:
                self.dev.mmc.setXYPosition(self.dev._mmDeviceNames['xy'], pos[0:1])
            if moveXY:
                self.dev.mmc.setPosition(self.dev._mmDeviceNames['z'], pos[2])
        
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

        for ax in self._axes:
            if self.dev.mmc.deviceBusy(self.dev._mmDeviceNames[ax]):
                # Still moving
                return 0

        # did we reach target?
        pos = self.dev._getPosition()
        dif = ((np.array(pos) - np.array(self.targetPos))**2).sum()**0.5
        if dif < 2.5e-6:
            # reached target
            self._finished = True
            return 1
        else:
            # missed
            self._finished = True
            self._interrupted = True
            self._errorMsg = "Move did not complete (target=%s, position=%s, dif=%s)." % (self.targetPos, pos, dif)
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



class MicroManagerGUI(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)
