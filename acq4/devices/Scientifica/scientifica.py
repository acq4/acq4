from __future__ import annotations

import contextlib
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
        name = config.pop("name", None)

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

        self.setUserSpeed(config.get("userSpeed", self.dev.getSpeed() * 1e-6))

        # whether to monitor for changes to a MOC
        self.monitorObj = config.get("monitorObjective", False)
        if self.monitorObj is True:
            self.objectiveState = None
            self._checkObjective()

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
            self.dev.stop()
            if self._lastMove is not None:
                self._lastMove._stopped()
            self._lastMove = None

    def abort(self):
        """Stop the manipulator immediately."""
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

    def _checkObjective(self):
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
        self.monitorObj = monitorObj
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

                pos = self.dev._getPosition()  # this causes sigPositionChanged to be emitted
                if pos != lastPos:
                    # if there was a change, then loop more rapidly for a short time.
                    interval = self.minInterval
                    lastPos = pos
                else:
                    interval = min(maxInterval, interval * 2)

                if self.monitorObj is True:
                    self.dev._checkObjective()

                time.sleep(interval)
            except Exception:
                debug.printExc("Error in Scientifica monitor thread:")
                time.sleep(maxInterval)


class ScientificaMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Scientifica manipulator."""

    def __init__(self, dev, pos, speed, userSpeed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMsg = None
        self._finished = False
        pos = np.array(pos)
        with self.dev.dev.lock:
            self.dev.dev.moveTo(pos, speed / 1e-6)
            # reset to user speed immediately after starting move
            # (the move itself will run with the previous speed)
            self.dev.dev.setSpeed(userSpeed / 1e-6)

    def wasInterrupted(self):
        """Return True if the move was interrupted before completing."""
        return self._interrupted

    def isDone(self):
        """Return True if the move is complete."""
        return self._getStatus() != 0

    def _getStatus(self):
        """Check status of move unless we already know it is complete.
        Return:
            0: still moving; 1: finished successfully; -1: finished unsuccessfully
        """
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
        dif = ((np.array(pos) - np.array(self.targetPos)) ** 2).sum() ** 0.5
        self._finished = True
        if dif < 1.0:  # reached target
            return 1
        else:  # missed
            self._interrupted = True
            self._errorMsg = f"Move did not complete (target={self.targetPos}, position={pos}, dif={dif})."
            return -1

    def _stopped(self):
        # Called when the manipulator is stopped, possibly interrupting this move.
        startTime = ptime.time()
        while True:
            status = self._getStatus()
            if status == 1:
                # finished; ignore stop
                return
            elif status == -1:
                self._errorMsg = "Move was interrupted before completion."
                return
            elif status == 0 and ptime.time() < startTime + 0.15:
                # allow 150ms to stop
                continue
            elif status == 0:
                # not actually stopped! This should not happen.
                raise RuntimeError("Interrupted move but manipulator is still running!")
            else:
                raise ValueError(f"Unknown status: {status}")

    def errorMessage(self):
        return self._errorMsg


class ScientificaCalibrationWindow(StageAxesCalibrationWindow):
    def __init__(self, device: Stage):
        super().__init__(device)
        self._timer = None
        if device.getStoredLocation('zLimit') is None:
            limit_text = 'Save Z limit'
        else:
            limit_text = 'Calibrate using Z limit'
        self._zLimitCalibrateBtn = Qt.QPushButton(limit_text)
        self._zLimitCalibrateBtn.setToolTip(
            'This will raise the stage to its Z limit and use that to set the global transform. The first time you use '
            'this, the stage should already be calibrated. That calibration will be restored thereafter. ACQ4 limits '
            'will be disabled for the duration of this operation. This will take ~20s.'
        )
        self._layout.addWidget(self._zLimitCalibrateBtn, 2, 0)
        self._zLimitCalibrateBtn.clicked.connect(self.calibrateZLimit)
        self._savedLimits = None
        self._calibrationFuture = None
        self._transformAdjustment = None

        self._clearSavedZLimitBtn = Qt.QPushButton('Clear saved Z limit')
        self._clearSavedZLimitBtn.setToolTip(
            'If the stage has genuinely changed its position, you should clear the old calibration.')
        self._layout.addWidget(self._clearSavedZLimitBtn, 2, 1)
        self._clearSavedZLimitBtn.clicked.connect(self.clearSavedZLimit)

    def calibrateZLimit(self):
        self._zLimitCalibrateBtn.setEnabled(False)
        self._zLimitCalibrateBtn.setText('Calibrating...')
        self._calibrationFuture = self._doZLimitCalibration()
        self._calibrationFuture.sigFinished.connect(self._zLimitCalibrationFinished)

    @future_wrap
    def _doZLimitCalibration(self, _future: Future):
        with self._dev.lock:
            self._savedLimits = self._dev.getLimits()
            try:
                self._dev.setLimits(None, None, None)
                pos = self._dev.globalPosition()
                pos[2] += 1e27  # move to a very high position
                with contextlib.suppress(Future.Timeout, RuntimeError):
                    _future.waitFor(self._dev.moveToGlobal(pos, 'fast'), timeout=20)
                self._dev.stop()
                if self._dev.getStoredLocation('zLimit') is None:
                    self._dev.setStoredLocation('zLimit')
                else:
                    expected = self._dev.getStoredLocation('zLimit')[2]
                    actual = self._dev.globalPosition()[2]
                    diff = self._transformAdjustment = expected - actual
                    xform = SRTTransform3D(self._dev.deviceTransform())
                    xform.setTranslate(np.array(xform.getTranslation()) + [0, 0, diff])
                    self._dev.setDeviceTransform(xform)
            finally:
                self._dev.setLimits(*self._savedLimits)

    def _zLimitCalibrationFinished(self):
        try:
            self._calibrationFuture.wait()
            if self._transformAdjustment is not None:
                alert = Qt.QMessageBox()
                alert.setWindowTitle('Z calibrated')
                if abs(self._transformAdjustment) > 1e-15:
                    alert.setText(
                        f"Z limit calibration adjusted transform by {siFormat(self._transformAdjustment, suffix='m')}. "
                        f"You should adjust devices.cfg to match."
                    )
                else:
                    alert.setText('Z limit calibration detected to appreciable slippage.')
                alert.setStandardButtons(Qt.QMessageBox.Ok)
                alert.exec_()
        finally:
            self._calibrationFuture = None
            self._zLimitCalibrateBtn.setEnabled(True)
            self._zLimitCalibrateBtn.setText('Calibrate using Z limit')

    def clearSavedZLimit(self):
        self._clearSavedZLimitBtn.setEnabled(False)
        self._dev.clearStoredLocation('zLimit')
        self._clearSavedZLimitBtn.setText('Cleared')
        self._zLimitCalibrateBtn.setText('Save Z limit')
        self._clearSavedZLimitBtn.setStyleSheet('background-color: green; color: white;')
        self._timer = Qt.QTimer()
        self._timer.timeout.connect(self._resetClearSavedZLimitBtn)
        self._timer.setSingleShot(True)
        self._timer.start(4000)

    def _resetClearSavedZLimitBtn(self):
        self._clearSavedZLimitBtn.setEnabled(True)
        self._clearSavedZLimitBtn.setText('Clear saved Z limit')
        self._clearSavedZLimitBtn.setStyleSheet('')
        self._timer = None


class ScientificaGUI(StageInterface):
    def __init__(self, dev, win):
        StageInterface.__init__(self, dev, win)

        # Insert Scientifica-specific controls into GUI
        self.zeroBtn = Qt.QPushButton('Zero position')
        nextRow = self.layout.rowCount()
        self.layout.addWidget(self.zeroBtn, nextRow, 0, 1, 2)
        nextRow += 1

        self.psGroup = Qt.QGroupBox('Rotary Controller')
        self.layout.addWidget(self.psGroup, nextRow, 0, 1, 2)
        nextRow += 1

        self.psLayout = Qt.QGridLayout()
        self.psGroup.setLayout(self.psLayout)
        self.speedLabel = Qt.QLabel('Speed')
        self.speedSpin = SpinBox(value=self.dev.userSpeed, suffix='m/turn', siPrefix=True, dec=True, bounds=[1e-6, 10e-3])
        self.psLayout.addWidget(self.speedLabel, 0, 0)
        self.psLayout.addWidget(self.speedSpin, 0, 1)

        self.zeroBtn.clicked.connect(self.dev.dev.zeroPosition)
        self.speedSpin.valueChanged.connect(self.dev.setDefaultSpeed)

    def calibrateClicked(self):
        if self.calibrateWindow is None:
            if self.dev.isManipulator:
                self.calibrateWindow = ManipulatorAxesCalibrationWindow(self.dev)
            else:
                self.calibrateWindow = ScientificaCalibrationWindow(self.dev)
        self.calibrateWindow.show()
        self.calibrateWindow.raise_()
