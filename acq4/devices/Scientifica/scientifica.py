# -*- coding: utf-8 -*-
from __future__ import print_function
import time
import numpy as np
from acq4.util import Qt
from ..Stage import Stage, MoveFuture, StageInterface
from acq4.drivers.Scientifica import Scientifica as ScientificaDriver
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug, ptime, SpinBox


class Scientifica(Stage):
    """
    A Scientifica motorized device.

    This class supports PatchStar, MicroStar, SliceScope, objective changers, etc.
    The device may be identified either by its serial port or by its description 
    string:

        port: <serial port>  # eg. 'COM1' or '/dev/ttyACM0'
        name: <string>  # eg. 'SliceScope' or 'MicroStar 2'
        baudrate: <int>  #  may be 9600 or 38400

    The optional 'baudrate' parameter is used to set the baudrate of the device.
    Both valid rates will be attempted when initially connecting.
    """
    def __init__(self, man, config, name):
        # can specify 
        port = config.pop('port', None)
        name = config.pop('name', None)

        self.scale = config.pop('scale', (1e-6, 1e-6, 1e-6))
        baudrate = config.pop('baudrate', None)
        ctrl_version = config.pop('version', 2)
        try:
            self.dev = ScientificaDriver(port=port, name=name, baudrate=baudrate, ctrl_version=ctrl_version)
        except RuntimeError as err:
            if hasattr(err, 'dev_version'):
                raise RuntimeError(err.message + " You must add `version=%d` to the configuration for this device and double-check any speed/acceleration parameters." % int(err.dev_version))
            else:
                raise

        # Controllers reset their baud to 9600 after power cycle
        if baudrate is not None and self.dev.getBaudrate() != baudrate:
            self.dev.setBaudrate(baudrate)

        self._lastMove = None
        man.sigAbortAll.connect(self.abort)

        Stage.__init__(self, man, config, name)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        self.getPosition(refresh=True)

        # Set approach angle
        # Disabled--this toggles the approach bit and we can't reconfigure it from here :(
        # approach = self.dev.send('APPROACH')
        # self.dev.send('ANGLE %f' % self.pitch)
        # self.dev.send('APPROACH %s' % approach)  # reset approach bit; setting angle enables it

        # set any extra parameters specified in the config
        params = config.get('params', {})
        for param, val in params.items():
            if param == 'currents':
                assert len(val) == 2
                self.dev.setCurrents(*val)
            elif param == 'axisScale':
                assert len(val) == 3
                for i, x in enumerate(val):
                    self.dev.setAxisScale(i, x)
            else:
                self.dev.setParam(param, val)

        self.setUserSpeed(config.get('userSpeed', self.dev.getSpeed() * abs(self.scale[0])))
        
        # whether to monitor for changes to a MOC
        self.monitorObj = config.get('monitorObjective', False)
        if self.monitorObj is True:
            if self.dev._version < 3:
                raise TypeError("Scientifica motion card version %s does not support reading objective position." % self.dev._version)
            self.objectiveState = None
            self._checkObjective()

        # thread for polling position changes

        self.monitor = MonitorThread(self, self.monitorObj)
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

    def abort(self):
        """Stop the manipulator immediately.
        """
        self.dev.stop()
        if self._lastMove is not None:
            self._lastMove._stopped()
            self._lastMove = None

    def setUserSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under manual control.

        The stage's maximum speed is reset to this value when it is not under
        programmed control.
        """
        self.userSpeed = v
        self.dev.setSpeed(v / abs(self.scale[0]))

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
            speed = self._interpretSpeed(speed)

            self._lastMove = ScientificaMoveFuture(self, pos, speed, self.userSpeed)
            return self._lastMove

    def deviceInterface(self, win):
        return ScientificaGUI(self, win)

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity.
        """
        s = [int(-v * 1000. / 67. / self.scale[i]) for i,v in enumerate(vel)]
        print(s)
        self.dev.send('VJ %d %d %d C' % tuple(s))

    def _checkObjective(self):
        with self.lock:
            obj = int(self.dev.send('obj'))
            if obj != self.objectiveState:
                self.objectiveState = obj
                self.sigSwitchChanged.emit(self, {'objective': obj})

    def getSwitch(self, name):
        if name == 'objective' and self.monitorObj:
            return self.objectiveState
        else:
            return Stage.getSwitch(self, name)


class MonitorThread(Thread):
    """Thread to poll for manipulator position changes.
    """
    def __init__(self, dev, monitorObj):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self.monitorObj = monitorObj
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

                if self.monitorObj is True:
                    self.dev._checkObjective()

                time.sleep(interval)
            except:
                debug.printExc('Error in Scientifica monitor thread:')
                time.sleep(maxInterval)
                

class ScientificaMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Scientifica manipulator.
    """
    def __init__(self, dev, pos, speed, userSpeed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMSg = None
        self._finished = False
        pos = np.array(pos) / np.array(self.dev.scale)
        with self.dev.dev.lock:
            self.dev.dev.moveTo(pos, speed / abs(self.dev.scale[0]))
            # reset to user speed immediately after starting move
            # (the move itself will run with the previous speed)
            self.dev.dev.setSpeed(userSpeed / abs(self.dev.scale[0]))
        
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



class ScientificaGUI(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)

        # Insert Scientifica-specific controls into GUI
        self.zeroBtn = Qt.QPushButton('Zero position')
        self.layout.addWidget(self.zeroBtn, self.nextRow, 0, 1, 2)
        self.nextRow += 1

        self.psGroup = Qt.QGroupBox('Rotary Controller')
        self.layout.addWidget(self.psGroup, self.nextRow, 0, 1, 2)
        self.nextRow += 1

        self.psLayout = Qt.QGridLayout()
        self.psGroup.setLayout(self.psLayout)
        self.speedLabel = Qt.QLabel('Speed')
        self.speedSpin = SpinBox(value=self.dev.userSpeed, suffix='m/turn', siPrefix=True, dec=True, bounds=[1e-6, 10e-3])
        self.psLayout.addWidget(self.speedLabel, 0, 0)
        self.psLayout.addWidget(self.speedSpin, 0, 1)

        self.zeroBtn.clicked.connect(self.dev.dev.zeroPosition)
        self.speedSpin.valueChanged.connect(lambda v: self.dev.setDefaultSpeed(v))

