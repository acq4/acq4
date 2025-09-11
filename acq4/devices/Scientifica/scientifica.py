from __future__ import annotations

from typing import Optional

import numpy as np

from acq4.devices.Stage import Stage, MoveFuture, StageInterface
from acq4.drivers.Scientifica import Scientifica as ScientificaDriver
from acq4.util import Qt
from acq4.util.debug import logMsg
from acq4.util.future import future_wrap, Future, FutureButton
from acq4.util.threadrun import runInGuiThread
from pyqtgraph import SpinBox, siFormat


class Scientifica(Stage):
    """
    A Scientifica motorized device driver for manipulators and stages.
    
    * Supports PatchStar, MicroStar, SliceScope, objective changers, and other Scientifica devices.
    * Requires the ``pyserial`` package for serial communication.
    * Recommends Scientifica's LinLab software for initial configuration and testing, but note that
      ACQ4 will not be able to access the serial port while LinLab is running. 
    
    Configuration options:
    
    * **port** (str, optional): Serial port (e.g., 'COM1' or '/dev/ttyACM0')
      Either port or name must be specified.
    
    * **name** (str, optional): Device name as assigned in LinLab software
      (e.g., 'SliceScope' or 'MicroStar 2'). Either port or name must be specified.
    
    * **baudrate** (int, optional): Serial baud rate (9600 or 38400)
      Both rates will be attempted if not specified.
    
    * **version** (int, optional): Controller version (default: 2)
      Some devices require version=1 for compatibility.
    
    * **scale** (tuple, optional): (x, y, z) scale factors in m/step 
      (default: (1e-6, 1e-6, 1e-6))
    
    * **userSpeed** (float, optional): Default speed for manual control (m/sec).
      Sets the maximum speed when device is under manual control.
    
    * **autoZeroDirection** (tuple, optional): Auto-zero direction for each axis.
      This affects the direction traveled when "auto-set zero position" is clicked from the manager dock.
      (default: (-1, -1, -1)). Set to None to disable auto-zero for an axis.
    
    * **monitorObjective** (bool, optional): Monitor objective changer state
      (default: False). Set to True to track objective position changes.
    
    * **capabilities** (dict, optional): Override device capabilities
      Format: {"getPos": (x, y, z), "setPos": (x, y, z), "limits": (x, y, z)}
      where each tuple contains booleans for each axis.
    
    * **isManipulator** (bool, optional): Override manipulator detection
      If not specified, detection is automatic based on device type.
    
    * **params** (dict, optional): Low-level device parameters that are set on the device at ACQ4 startup time. 
      These may also be configured using LinLab, but we recommend setting them here in order to enforce
      consistent settings.
        - axisScale: (x, y, z) axis scaling factors affect the size and direction of steps reported by the device.
          The absolute value of these is determined by the manufacturer and should not be changed.
          The sign may be changed to flip the direction of the axis.
        - joyDirectionX/Y/Z: (bool) Used to switch the direction of the patch pad / patch cube rotary control for each axis.
          Note that the rotary control direction is also affected by the sign of the axisScale values.
        - minSpeed, maxSpeed: Speed limits in device units
        - maxZSpeed, minZSpeed: Z-axis specific speed limits (for devices with separate Z control)
        - accel: Acceleration setting
        - joySlowScale, joyFastScale: Joystick speed scaling
        - joyAccel: Joystick acceleration
        - approachAngle: Approach mode angle (degrees)
        - approachMode: Approach mode enabled (bool)
          Note: the approach mode is also set using a physical switch on the device; setting this parameter
          here may cause the device to behave contrary to the physical switch state until it is toggled.
        - objLift: Distance to lift objectives before switching (int; 1 = 10 nm)
          Note: the sign of this distance depends on the sign of the Z axisScale parameter.
        - objDisp: Distance between focal planes of objectives (int; 1 = 10 nm)
          Note: the sign of this distance depends on the sign of the Z axisScale parameter.
        - objL1, objL2: Legacy objective switching parameters for version 2 devices (int)
        - currents: Motor current limits (not recommended to change these; be careful to follow manufacturer specs!)
    
    Example configuration::
    
        SliceScope:
            driver: 'Scientifica'
            name: 'SliceScope'
            scale: [-1e-6, -1e-6, 1e-6]
            params:
                axisScale: [5.12, -5.12, -6.4]
                joyDirectionX: True
                joyDirectionY: True
                joyDirectionZ: False
                minSpeed: 1000
                maxSpeed: 30000
                accel: 500
                joySlowScale: 4
                joyFastScale: 80
                joyAccel: 500
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
            self.driver = ScientificaDriver(port=port, name=name, baudrate=baudrate, ctrl_version=ctrl_version)
        except RuntimeError as err:
            if hasattr(err, "dev_version"):
                raise RuntimeError(
                    f"You must add `version={int(err.dev_version)}` to the configuration for this "
                    f"device and double-check any speed/acceleration parameters."
                ) from err
            else:
                raise

        if 'isManipulator' not in config:
            config['isManipulator'] = self.driver.isManipulator()

        # Controllers reset their baud to 9600 after power cycle
        if baudrate is not None and self.driver.getBaudrate() != baudrate:
            self.driver.setBaudrate(baudrate)

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
                self.driver.setCurrents(*val)
            elif param == "axisScale":
                assert len(val) == 3
                for i, x in enumerate(val):
                    self.driver.setAxisScale(i, x)
            else:
                self.driver.setParam(param, val)

        self.userSpeed = None
        self.setUserSpeed(config.get("userSpeed", self._interpretSpeed('fast')))

        self.autoZeroDirection = config.get('autoZeroDirection', (-1, -1, -1))

        self.driver.setPositionCallback(self._stageReportedPositionChange)

        # whether to monitor for changes to a MOC
        self.monitorObj = config.get("monitorObjective", False)
        if self.monitorObj is True:            
            self.objectiveState = self.driver.getObjective()
            self.driver.setObjectiveCallback(self._stageReportedObjectiveChange)

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
        self.driver.stop()
        if self._lastMove is not None:
            self._lastMove.interrupt()
            self._lastMove = None

    def setUserSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under manual control.

        The stage's maximum speed is reset to this value when it is not under
        programmed control.
        """
        self.userSpeed = v
        self.driver.setDefaultSpeed(v * 1e6)  # requires um/s

    @property
    def positionUpdatesPerSecond(self):
        return 1.0 / self.driver.ctrlThread.poll_interval

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = self.driver.getPos()
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
        self.driver.close()
        Stage.quit(self)

    def _move(self, pos, speed, linear, **kwds):
        with self.lock:
            if self._lastMove is not None and not self._lastMove.isDone():
                self.stop()
            speed = self._interpretSpeed(speed)

            self._lastMove = ScientificaMoveFuture(self, pos, speed, **kwds)
            return self._lastMove

    def deviceInterface(self, win):
        return ScientificaGUI(self, win)

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity."""
        s = [int(1e8 * v) for v in vel]
        self.driver.send("VJ -%d %d %d" % tuple(s))

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
    def __init__(self, dev: Scientifica, pos, speed: float, **kwds):
        self._moveReq = dev.driver.moveTo(np.array(pos), speed / 1e-6, **kwds)
        targetPos = self._moveReq.target_pos  # will have None values filled in with current position
        super().__init__(dev, targetPos, speed)
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

        if dev.capabilities()["getPos"][0] and dev.autoZeroDirection[0] is not None:
            self.xZeroBtn = Qt.QPushButton("Zero X")
            self.xZeroBtn.clicked.connect(self.zeroX)
            self.layout.addWidget(self.xZeroBtn, nextRow, 0)
            self.autoXZeroBtn = FutureButton(self.autoXZero, "Auto-set X zero", stoppable=True)
            self.layout.addWidget(self.autoXZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][1] and dev.autoZeroDirection[1] is not None:
            self.yZeroBtn = Qt.QPushButton("Zero Y")
            self.yZeroBtn.clicked.connect(self.zeroY)
            self.layout.addWidget(self.yZeroBtn, nextRow, 0)
            self.autoYZeroBtn = FutureButton(self.autoYZero, "Auto-set Y zero", stoppable=True)
            self.layout.addWidget(self.autoYZeroBtn, nextRow, 1)
            nextRow += 1

        if dev.capabilities()["getPos"][2] and dev.autoZeroDirection[2] is not None:
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
        self.dev.driver.zeroPosition()

    def zeroX(self):
        self.dev.driver.zeroPosition('X')

    def zeroY(self):
        self.dev.driver.zeroPosition('Y')

    def zeroZ(self):
        self.dev.driver.zeroPosition('Z')

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
            f"This will move {self.dev.name()} to its limit. Please ensure such a movement is safe. Ready?",
            Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel,
        )
        if response != Qt.QMessageBox.Ok:
            self.sigBusyMoving.emit(False)
            return Future.immediate(error="User requested stop", stopped=True)

        return self._doAutoZero(axis)

    @future_wrap
    def _doAutoZero(self, axis: int = None, _future: Future = None) -> None:
        self._savedLimits = self.dev.getLimits()
        try:
            diff = np.zeros(3)  # keep track of offset changes
            self.dev.setLimits(None, None, None)
            globalStartPos = self.dev.globalPosition()

            # move to an excessively far position until we hit a limit switch
            far_away = [None if x is None else 1e6 * x for x in self.dev.autoZeroDirection]
            if axis is not None and far_away[axis] is None:
                raise Exception(f"Requested auto zero for axis {'XYZ'[axis]}, but autoZeroDirection is disabled for this axis in the configuration.")

            self._moveAndWait(far_away, axis, _future)
            diff += self._zeroAxis(axis)

            # This part is a pain: if the approach switch is enabled on the control cube, then it's possible for the
            # X limit switch to stop the Z axis and vice-versa. To work around this, we need to calibrate
            # these axes independently while ensuring that the other is moved away from its limit switch.
            if self.dev.isManipulator and axis != 1:
                for axis in (0, 2):
                    otherAxis = 2 - axis
                    # Move z (or x) 300 um in either direction, then try moving x (or z) far away.
                    # If z (or x) is already at its limit, then at least one of these should get x (or z)
                    # to its limit.
                    # We need to try both directions because we don't know which limit switch is activated.
                    for dir in (1, -1):
                        currentPos = self.dev.getPosition()
                        currentPos[otherAxis] += 300 * dir
                        # small step to move z (x) away from its limit switch
                        self._moveAndWait(currentPos, otherAxis, _future)
                        # far step to get x (z) to its limit switch
                        self._moveAndWait(far_away, axis, _future)
                        diff += self._zeroAxis(axis)

            logMsg(f"Auto-zeroed {self.dev.name()} by {diff}")
            move_future = self.dev.moveToGlobal(globalStartPos + diff, "fast")
            slippedAxes = np.abs(diff) > 50e-6
            if np.any(slippedAxes):
                msg = f"Detected axis slip on {self.dev.name()}:"
                for ax, slip in enumerate(slippedAxes):
                    if slip:
                        axis = 'XYZ'[ax]
                        msg = f"{msg} {axis}={siFormat(diff[ax], suffix='m')}"
                runInGuiThread(Qt.QMessageBox.warning, self, "Large slippage detected", msg, Qt.QMessageBox.Ok)
            _future.waitFor(move_future)
        finally:
            self.sigBusyMoving.emit(False)
            self.dev.stop()
            self.dev.setLimits(*self._savedLimits)

    def _moveAndWait(self, pos, axis, _future):
        """Move to pos and wait for the move to complete. 
        If axis is None, move all three axes to the specified position.
        If axis is 0,1,2, move only the specified axis to pos[axis].

        If the future does not reach its target, this is silently ignored.

        Return True if the manipulator reached its target.
        """
        if axis is None:
            dest = pos
        else:
            dest = [None, None, None]
            dest[axis] = pos[axis]
        f = self.dev._move(dest, "fast", False, attempts_allowed=1)
        while not f.isDone():
            _future.sleep(0.1)

        # raise errors not related to missing the target
        missed = f.wasInterrupted() and 'Stopped moving before reaching target' in f.errorMessage()
        if f.wasInterrupted() and not missed:
            f.wait()

        return not missed

    def _zeroAxis(self, axis):
        """Zero an axis (or all three) and return the vector change in global position."""
        before = self.dev.globalPosition()
        if axis is None:
            self.dev.driver.zeroPosition()
        else:
            self.dev.driver.zeroPosition('XYZ'[axis])
        self.dev.getPosition(refresh=True)
        after = self.dev.globalPosition()
        diff = np.array(after) - np.array(before)
        return diff
