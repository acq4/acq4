from __future__ import annotations

import contextlib
from typing import Optional

import numpy as np
import time

import numpy as np

from acq4.drivers.Scientifica import Scientifica as ScientificaDriver
from acq4.util import Qt, ptime
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from pyqtgraph import debug, SpinBox, FeedbackButton
from ..Stage import Stage, MoveFuture, StageInterface
from ...util.future import future_wrap, Future


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
        port = config.pop("port", None)
        name = config.pop("name", name)

        # if user has not provided scale values, we can make a guess
        config.setdefault("scale", (1e-6, 1e-6, 1e-6))

        baudrate = config.pop("baudrate", None)
        ctrl_version = config.pop("version", 2)
        try:
            self.dev = ScientificaDriver(port=port, name=name, baudrate=baudrate, ctrl_version=ctrl_version)
        except RuntimeError as err:
            if hasattr(err, "dev_version"):
                raise RuntimeError(
                    f"You must add `version={int(err.dev_version)}` to the configuration for this "
                    f"device and double-check any speed/acceleration parameters."
                ) from err
            else:
                raise

        # Controllers reset their baud to 9600 after power cycle
        if baudrate is not None and self.dev.getBaudrate() != baudrate:
            self.dev.setBaudrate(baudrate)

        self._lastMove: Optional[ScientificaMoveFuture] = None
        man.sigAbortAll.connect(self.abort)

        super().__init__(man, config, name)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        self.getPosition(refresh=True)

        # Set approach angle
        # Disabled--this toggles the approach bit and we can't reconfigure it from here :(
        # approach = self.dev.send('APPROACH')
        # self.dev.send('ANGLE %f' % self.pitch)
        # self.dev.send('APPROACH %s' % approach)  # reset approach bit; setting angle enables it

        # set any extra parameters specified in the config
        params = config.get("params", {})
        for param, val in params.items():
            if param == "currents":
                assert len(val) == 2
                self.dev.setCurrents(*val)
            elif param == "axisScale":
                assert len(val) == 3
                for i, x in enumerate(val):
                    self.dev.setAxisScale(i, x)
            else:
                self.dev.setParam(param, val)

        self.userSpeed = None
        self.setUserSpeed(config.get("userSpeed", self.dev.getSpeed() * 1e-6))

        # whether to monitor for changes to a MOC
        self.monitorObj = config.get("monitorObjective", False)
        if self.monitorObj is True:
            self.objectiveState = None
            self.checkObjective()

        # thread for polling position changes

        self.monitor = MonitorThread(self, self.monitorObj)
        self.monitor.start()

    def axes(self):
        return "x", "y", "z"

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if "capabilities" in self.config:
            return self.config["capabilities"]
        else:
            return {
                "getPos": (True, True, True),
                "setPos": (True, True, True),
                "limits": (False, False, False),
            }

    def stop(self):
        """Stop the manipulator immediately."""
        with self.lock:
            self.abort()

    def abort(self):
        """Stop the manipulator immediately."""
        self.dev.stop()
        if self._lastMove is not None:
            self._lastMove.interrupt()
            self._lastMove = None

    def setUserSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under manual control.

        The stage's maximum speed is reset to this value when it is not under
        programmed control.
        """
        self.userSpeed = v
        self.dev.setSpeed(v * 1e6)  # requires um/s

    @property
    def positionUpdatesPerSecond(self):
        return 1.0 / self.monitor.minInterval

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = self.dev.getPos()
            if pos != self._lastPos:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos

    def checkForMoveComplete(self, refresh=True):
        if self._lastMove is not None and not self._lastMove.isDone():
            self._lastMove.checkForComplete(refresh=refresh)

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def quit(self):
        if hasattr(self, "monitor"):  # in case __init__ failed
            self.monitor.stop()
        Stage.quit(self)

    def _move(self, pos, speed, linear, **kwds):
        with self.lock:
            if self._lastMove is not None and not self._lastMove.isDone():
                self.stop()
            speed = self._interpretSpeed(speed)

            self._lastMove = ScientificaMoveFuture(self, pos, speed, self.userSpeed)
            return self._lastMove

    def deviceInterface(self, win):
        return ScientificaGUI(self, win)

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity."""
        s = [int(1e8 * v) for v in vel]
        self.dev.send("VJ -%d %d %d" % tuple(s))

    def checkObjective(self):
        with self.lock:
            obj = int(self.dev.send("obj"))
            if obj != self.objectiveState:
                self.objectiveState = obj
                self.sigSwitchChanged.emit(self, {"objective": obj})

    def getSwitch(self, name):
        if name == "objective" and self.monitorObj:
            return self.objectiveState
        else:
            return Stage.getSwitch(self, name)


class MonitorThread(Thread):
    """Thread to poll for manipulator position changes."""

    def __init__(self, dev, monitorObj):
        self.dev = dev
        self.lock = Mutex(recursive=True)
        self._monitorObjective = monitorObj
        self.stopped = False
        self.interval = 300e-3
        self.minInterval = 100e-3

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
        interval = self.minInterval
        lastPos = None
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    maxInterval = self.interval

                pos = self.dev.getPosition(refresh=True)  # this causes sigPositionChanged to be emitted
                if pos != lastPos:
                    # if there was a change, then loop more rapidly for a short time.
                    interval = self.minInterval
                    lastPos = pos
                else:
                    # we just refreshed our position, so no need to do it again immediately
                    self.dev.checkForMoveComplete(refresh=False)
                    interval = min(maxInterval, interval * 2)

                if self._monitorObjective is True:
                    self.dev.checkObjective()

                time.sleep(interval)
            except Exception:
                debug.printExc("Error in Scientifica monitor thread:")
                time.sleep(maxInterval)


class ScientificaMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Scientifica manipulator.
    """
    def __init__(self, dev: Scientifica, pos, speed: float, userSpeed: float):
        super().__init__(dev, pos, speed)
        self._errorMsg = None
        pos = np.array(pos)
        with self.dev.dev.lock:
            self.dev.dev.moveTo(pos, speed / 1e-6)
            # reset to user speed immediately after starting move
            # (the move itself will run with the previous speed)
            self.dev.dev.setSpeed(userSpeed / 1e-6)

    def checkForComplete(self, refresh=True):
        if self.isDone():
            return
        status = self._getStatus(refresh=refresh)
        if status == 1:
            self._taskDone()
        elif status == -1:
            self._taskDone(interrupted=True, error=self._errorMsg)

    def _getStatus(self, refresh=True):
        """Check status of move unless we already know it is complete.
        Return:
            0: still moving; 1: finished successfully; -1: finished unsuccessfully
        """
        if self.isDone():
            if self.wasInterrupted():
                return -1
            else:
                return 1
        if self.dev.dev.isMoving():
            # Still moving
            return 0
        # did we reach target?
        pos = self.dev.getPosition(refresh=refresh)
        dif = np.linalg.norm(np.array(pos) - np.array(self.targetPos))
        if dif < 1.0:  # reached target
            return 1
        # missed
        return -1

    def interrupt(self):
        # Called when the manipulator is stopped, possibly interrupting this move.
        startTime = ptime.time()
        while True:
            status = self._getStatus()
            if status == 1:
                # finished; ignore stop
                break
            elif status == -1:
                self._errorMsg = "Move was interrupted before completion."
                break
            elif status == 0 and ptime.time() < startTime + 0.15:
                # allow 150ms to stop
                self.sleep(0.05)
                continue
            elif status == 0:
                # not actually stopped! This should not happen.
                raise RuntimeError("Interrupted move but manipulator is still running!")
            else:
                raise ValueError(f"Unknown status: {status}")
        self.checkForComplete()

    def errorMessage(self):
        return self._errorMsg


class ScientificaGUI(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)
        nextRow = self.layout.rowCount()

        # Insert Scientifica-specific controls into GUI
        self.zeroBtn = Qt.QPushButton("Zero position")
        self.zeroBtn.setToolTip("Set the current position as the new zero position on all axes.")
        self.zeroBtn.clicked.connect(self.dev.dev.zeroPosition)
        self.layout.addWidget(self.zeroBtn, nextRow, 0)

        self.autoZeroBtn = FeedbackButton("Auto-set zero position")
        self.autoZeroBtn.setToolTip(
            "Drive to the mechanical limit in each axis and set that as the zero position. Please ensure that the "
            "device is not obstructed before using this feature."
        )
        self.autoZeroBtn.clicked.connect(self.autoZero)
        self.layout.addWidget(self.autoZeroBtn, nextRow, 1)
        self._autoZeroFuture = None
        nextRow += 1

        if dev.capabilities()["getPos"][0]:
            self.xZeroBtn = Qt.QPushButton("Zero X")
            self.xZeroBtn.clicked.connect(self.zeroX)
            self.layout.addWidget(self.xZeroBtn, nextRow, 0)
            self.autoXZeroBtn = FeedbackButton("Auto-set X zero")
            self.autoXZeroBtn.clicked.connect(self.autoXZero)
            self.layout.addWidget(self.autoXZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][1]:
            self.yZeroBtn = Qt.QPushButton("Zero Y")
            self.yZeroBtn.clicked.connect(self.zeroY)
            self.layout.addWidget(self.yZeroBtn, nextRow, 0)
            self.autoYZeroBtn = FeedbackButton("Auto-set Y zero")
            self.autoYZeroBtn.clicked.connect(self.autoYZero)
            self.layout.addWidget(self.autoYZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][2]:
            self.zZeroBtn = Qt.QPushButton("Zero Z")
            self.zZeroBtn.clicked.connect(self.zeroZ)
            self.layout.addWidget(self.zZeroBtn, nextRow, 0)
            self.autoZZeroBtn = FeedbackButton("Auto-set Z zero")
            self.autoZZeroBtn.clicked.connect(self.autoZZero)
            self.layout.addWidget(self.autoZZeroBtn, nextRow, 1)
            nextRow += 1

        self.psGroup = Qt.QGroupBox("Rotary Controller")
        self.layout.addWidget(self.psGroup, nextRow, 0, 1, 2)
        nextRow += 1

        self.psLayout = Qt.QGridLayout()
        self.psGroup.setLayout(self.psLayout)
        self.speedLabel = Qt.QLabel("Speed")
        self.speedSpin = SpinBox(
            value=self.dev.userSpeed, suffix="m/turn", siPrefix=True, dec=True, bounds=[1e-6, 10e-3]
        )
        self.speedSpin.valueChanged.connect(self.dev.setDefaultSpeed)
        self.psLayout.addWidget(self.speedLabel, 0, 0)
        self.psLayout.addWidget(self.speedSpin, 0, 1)

    def zeroX(self):
        self.dev.dev.zeroPosition('X')

    def zeroY(self):
        self.dev.dev.zeroPosition('Y')

    def zeroZ(self):
        self.dev.dev.zeroPosition('Z')

    def autoZero(self):
        self._autoZero()

    def autoXZero(self):
        self._autoZero(axis=0)

    def autoYZero(self):
        self._autoZero(axis=1)

    def autoZZero(self):
        self._autoZero(axis=2)

    def _autoZero(self, axis: int | None = None):
        self.autoZeroBtn.processing("Moving...")
        self.autoXZeroBtn.processing("Moving...")
        self.autoYZeroBtn.processing("Moving...")
        self.autoZZeroBtn.processing("Moving...")
        self._autoZeroFuture = self._doAutoZero(axis)
        if axis is None:
            finisher = self.autoZeroFinished
        else:
            finisher = getattr(self, f"auto{'XYZ'[axis]}ZeroFinished")
        self._autoZeroFuture.sigFinished.connect(finisher)
        if self._autoZeroFuture.isDone():  # in case of instant completion
            finisher()

    @future_wrap
    def _doAutoZero(self, axis: int = None, _future: Future = None):
        self._savedLimits = self.dev.getLimits()
        try:
            self.dev.setLimits(None, None, None)
            pos = self.dev.globalPosition()
            far_away = [-1e27, -1e27, 1e27]
            if axis is None:
                pos = far_away
            else:
                pos[axis] = far_away[axis]
            print(f"moving to {pos}")
            self.dev.moveToGlobal(pos, "fast")
            _future.sleep(1)
            while self.dev.dev.isMoving():
                _future.sleep(0.1)
            self.dev.stop()
            self.dev.dev.zeroPosition('XYZ'[axis])
        finally:
            self.dev.setLimits(*self._savedLimits)

    def autoZeroFinished(self):
        self._autoZeroFinished()

    def autoXZeroFinished(self):
        self._autoZeroFinished(0)

    def autoYZeroFinished(self):
        self._autoZeroFinished(1)

    def autoZZeroFinished(self):
        self._autoZeroFinished(2)

    def _autoZeroFinished(self, axis=None):
        self.autoZeroBtn.setEnabled(True)
        self.autoZeroBtn.reset()
        self.autoXZeroBtn.setEnabled(True)
        self.autoXZeroBtn.reset()
        self.autoYZeroBtn.setEnabled(True)
        self.autoYZeroBtn.reset()
        self.autoZZeroBtn.setEnabled(True)
        self.autoZZeroBtn.reset()
        if axis is None:
            btn = self.autoZeroBtn
        else:
            btn = getattr(self, f"auto{'XYZ'[axis]}ZeroBtn")
        try:
            self._autoZeroFuture.wait()
        except Exception as e:
            btn.failure('Error!')
            raise e
        else:
            btn.success("Zero position set")
        finally:
            self._autoZeroFuture = None
