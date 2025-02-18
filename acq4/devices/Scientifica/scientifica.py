from __future__ import annotations

from typing import Optional

import numpy as np

from acq4.devices.Stage import Stage, MoveFuture, StageInterface
from acq4.drivers.Scientifica import Scientifica as ScientificaDriver
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException
from acq4.util.debug import logMsg
from acq4.util.future import future_wrap, Future, FutureButton
from pyqtgraph import SpinBox, siFormat


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
        self.setUserSpeed(config.get("userSpeed", self._interpretSpeed('fast')))

        self.dev.setPositionCallback(self._stageReportedPositionChange)

        # whether to monitor for changes to a MOC
        self.monitorObj = config.get("monitorObjective", False)
        if self.monitorObj is True:            
            self.objectiveState = self.dev.getObjective()
            self.dev.setObjectiveCallback(self._stageReportedObjectiveChange)

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
        self.dev.setDefaultSpeed(v * 1e6)  # requires um/s

    @property
    def positionUpdatesPerSecond(self):
        return 1.0 / self.dev.ctrlThread.poll_interval

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = self.dev.getPos()
            changed = pos != self._lastPos

        if changed:
            self._positionChanged(pos)

        return pos
    
    def _positionChanged(self, newPos):
        # can happen as a result of calling _getPosition, or if device poller
        # notices a position change
        self._lastPos = newPos
        self.posChanged(newPos)

    def _stageReportedPositionChange(self, nextPos):
        self._positionChanged(nextPos)

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def quit(self):
        self.dev.close()
        Stage.quit(self)

    def _move(self, pos, speed, linear, **kwds):
        with self.lock:
            if self._lastMove is not None and not self._lastMove.isDone():
                self.stop()
            speed = self._interpretSpeed(speed)

            self._lastMove = ScientificaMoveFuture(self, pos, speed)
            return self._lastMove

    def deviceInterface(self, win):
        return ScientificaGUI(self, win)

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity."""
        s = [int(1e8 * v) for v in vel]
        self.dev.send("VJ -%d %d %d" % tuple(s))

    def _objectiveChanged(self, obj):
        self.objectiveState = obj
        self.sigSwitchChanged.emit(self, {"objective": obj})

    def _stageReportedObjectiveChange(self, obj):
        self._objectiveChanged(obj)

    def getSwitch(self, name):
        if name == "objective" and self.monitorObj:
            return self.objectiveState
        else:
            return Stage.getSwitch(self, name)


class ScientificaMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Scientifica manipulator.
    """
    def __init__(self, dev: Scientifica, pos, speed: float):
        super().__init__(dev, pos, speed)
        pos = np.array(pos)
        self._moveReq = self.dev.dev.moveTo(pos, speed / 1e-6)
        self._moveReq.set_callback(self._requestFinished)

    def _requestFinished(self, moveReq):
        try:
            moveReq.wait(timeout=None)
            self._taskDone()
        except Exception as exc:
            self._taskDone(
                interrupted=True,
                error=moveReq.error,
                excInfo=moveReq.exc_info,
            )

    def interrupt(self):
        self._moveReq.cancel()


class ScientificaGUI(StageInterface):
    sigBusyMoving = Qt.Signal(object)  # button in use or False

    def __init__(self, dev, win):
        super().__init__(dev, win)
        self.sigBusyMoving.connect(self._setBusy)
        nextRow = self.layout.rowCount()

        # Insert Scientifica-specific controls into GUI
        self.zeroBtn = Qt.QPushButton("Zero position")
        self.zeroBtn.setToolTip("Set the current position as the new zero position on all axes.")
        self.zeroBtn.clicked.connect(self.zeroAll)
        self.layout.addWidget(self.zeroBtn, nextRow, 0)

        self.autoZeroBtn = FutureButton(self.autoZero, "Auto-set zero position", stoppable=True)
        self.autoZeroBtn.setToolTip(
            "Drive to the mechanical limit in each axis and set that as the zero position. Please ensure that the "
            "device is not obstructed before using this feature."
        )
        self.layout.addWidget(self.autoZeroBtn, nextRow, 1)
        nextRow += 1
        self.autoXZeroBtn = self.autoYZeroBtn = self.autoZZeroBtn = None

        if dev.capabilities()["getPos"][0]:
            self.xZeroBtn = Qt.QPushButton("Zero X")
            self.xZeroBtn.clicked.connect(self.zeroX)
            self.layout.addWidget(self.xZeroBtn, nextRow, 0)
            self.autoXZeroBtn = FutureButton(self.autoXZero, "Auto-set X zero", stoppable=True)
            self.layout.addWidget(self.autoXZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][1]:
            self.yZeroBtn = Qt.QPushButton("Zero Y")
            self.yZeroBtn.clicked.connect(self.zeroY)
            self.layout.addWidget(self.yZeroBtn, nextRow, 0)
            self.autoYZeroBtn = FutureButton(self.autoYZero, "Auto-set Y zero", stoppable=True)
            self.layout.addWidget(self.autoYZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][2]:
            self.zZeroBtn = Qt.QPushButton("Zero Z")
            self.zZeroBtn.clicked.connect(self.zeroZ)
            self.layout.addWidget(self.zZeroBtn, nextRow, 0)
            self.autoZZeroBtn = FutureButton(self.autoZZero, "Auto-set Z zero", stoppable=True)
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

    def _setBusy(self, busy_btn: bool | Qt.QPushButton):
        self.autoZeroBtn.setEnabled(busy_btn == self.autoZeroBtn or not busy_btn)
        if self.autoXZeroBtn:
            self.autoXZeroBtn.setEnabled(busy_btn == self.autoXZeroBtn or not busy_btn)
        if self.autoYZeroBtn:
            self.autoYZeroBtn.setEnabled(busy_btn == self.autoYZeroBtn or not busy_btn)
        if self.autoZZeroBtn:
            self.autoZZeroBtn.setEnabled(busy_btn == self.autoZZeroBtn or not busy_btn)

    def zeroAll(self):
        self.dev.dev.zeroPosition()

    def zeroX(self):
        self.dev.dev.zeroPosition('X')

    def zeroY(self):
        self.dev.dev.zeroPosition('Y')

    def zeroZ(self):
        self.dev.dev.zeroPosition('Z')

    def autoZero(self):
        self.sigBusyMoving.emit(self.autoZeroBtn)
        return self._autoZero()

    def autoXZero(self):
        self.sigBusyMoving.emit(self.autoXZeroBtn)
        return self._autoZero(axis=0)

    def autoYZero(self):
        self.sigBusyMoving.emit(self.autoYZeroBtn)
        return self._autoZero(axis=1)

    def autoZZero(self):
        self.sigBusyMoving.emit(self.autoZZeroBtn)
        return self._autoZero(axis=2)

    def _autoZero(self, axis: int | None = None):
        # confirm with user that movement is safe
        response = Qt.QMessageBox.question(
            self,
            "Caution: check for obstructions",
            "This will move the stage to its limit. Please ensure such a movement is safe. Ready?",
            Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel,
        )
        if response != Qt.QMessageBox.Ok:
            return Future.immediate(
                error="User requested stop", excInfo=(Future.StopRequested, Future.StopRequested(), None)
            )

        return self._doAutoZero(axis)

    @future_wrap
    def _doAutoZero(self, axis: int = None, _future: Future = None) -> None:
        self._savedLimits = self.dev.getLimits()
        try:
            self.dev.setLimits(None, None, None)
            pos = self.dev.getPosition()
            globalStartPos = self.dev.globalPosition()
            dest = pos[:]
            far_away = [-1e6, -1e6, -1e6]
            if axis is None:
                dest = far_away
            else:
                dest[axis] = far_away[axis]
            self.dev.move(dest, "fast")
            _future.sleep(1)
            while self.dev.dev.isMoving():
                _future.sleep(0.1)
            self.dev.stop()
            before = self.dev.globalPosition()
            if axis is None:
                self.dev.dev.zeroPosition()
            else:
                self.dev.dev.zeroPosition('XYZ'[axis])
            self.dev.getPosition(refresh=True)
            after = self.dev.globalPosition()
            diff = np.array(after) - np.array(before)
            logMsg(f"Auto-zeroed {self.dev.name()} by {diff}")
            _future.waitFor(self.dev.moveToGlobal(globalStartPos + diff, "fast"))
            slippedAxes = np.abs(diff) > 50e-6
            if np.any(slippedAxes):
                msg = f"Detected axis slip on {self.dev.name()}:"
                for ax, slip in enumerate(slippedAxes):
                    if slip:
                        axis = 'XYZ'[ax]
                        msg = f"{msg} {axis}={siFormat(diff[ax], suffix='m')}"
                Qt.QMessageBox.warning(self, "Slippage detected", msg, Qt.QMessageBox.Ok)
        finally:
            self.dev.stop()
            self.dev.setLimits(*self._savedLimits)
            self.sigBusyMoving.emit(False)
