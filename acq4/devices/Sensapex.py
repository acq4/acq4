# -*- coding: utf-8 -*-
from __future__ import print_function

import threading
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph import ptime, Transform3D, solve3DTransform

from acq4.util import Qt
from acq4.drivers.sensapex import UMP, version_info
from .Stage import Stage, MoveFuture, ManipulatorAxesCalibrationWindow, StageAxesCalibrationWindow


class Sensapex(Stage):
    """
    A Sensapex manipulator.
    """

    _sigRestartUpdateTimer = Qt.Signal(object)  # timeout duration

    devices = {}

    def __init__(self, man, config: dict, name):
        self.devid = config.get("deviceId")
        config.setdefault("isManipulator", self.devid < 20)
        self.scale = config.pop("scale", (1e-6, 1e-6, 1e-6))
        self.xPitch = config.pop("xPitch", 0)  # angle of x-axis. 0=parallel to xy plane, 90=pointing downward
        self.maxMoveError = config.pop("maxError", 1e-6)
        self._force_linear_movement = config.get("forceLinearMovement", False)

        address = config.pop("address", None)
        address = None if address is None else address.encode()
        group = config.pop("group", None)
        ump = UMP.get_ump(address=address, group=group)
        # create handle to this manipulator
        if "nAxes" in config and version_info < (1, 22, 4):
            raise RuntimeError("nAxes support requires version >= 1.022.4 of the sensapex-py library")
        self.dev = ump.get_device(self.devid, n_axes=config.get("nAxes", None))

        Stage.__init__(self, man, config, name)
        # Read position updates on a timer to rate-limit
        self._updateTimer = Qt.QTimer()
        self._updateTimer.timeout.connect(self._getPosition)
        self._lastUpdate = 0

        self._sigRestartUpdateTimer.connect(self._restartUpdateTimer)

        if "maxAcceleration" in config:
            self.dev.set_max_acceleration(config["maxAcceleration"])

        self.dev.add_callback(self._positionChanged)

        # force cache update for this device.
        # This should also verify that we have a valid device ID
        self.dev.get_pos()

        self._lastMove = None
        man.sigAbortAll.connect(self.stop)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        self.getPosition(refresh=True)

        # TODO: set any extra parameters specified in the config
        Sensapex.devices[self.devid] = self

    def axes(self):
        return ("x", "y", "z")[:self.dev.n_axes()]

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

    def axisTransform(self):
        if self._axisTransform is None:
            # sensapex manipulators do not have orthogonal axes, so we set up a 3D transform to compensate:
            a = self.xPitch * np.pi / 180.0
            s = self.scale
            pts1 = np.array([  # unit vector in sensapex space
                [0, 0, 0],
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 1],
            ])
            pts2 = np.array([  # corresponding vector in global space
                [0, 0, 0],
                [s[0] * np.cos(a), 0, -s[0] * np.sin(a)],
                [0, s[1], 0],
                [0, 0, s[2]],
            ])
            tr = solve3DTransform(pts1, pts2)
            tr[3, 3] = 1
            self._axisTransform = Transform3D(tr)
            self._inverseAxisTransform = None
        return self._axisTransform

    def stop(self):
        """Stop the manipulator immediately.
        """
        with self.lock:
            self.dev.stop()
            # also stop the last move since it might be stepwise and just keep requesting more steps
            lastMove = self._lastMove
            if lastMove is not None:
                lastMove.stop()
            self._lastMove = None

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            # using timeout=0 forces read from cache (the monitor thread ensures
            # these values are up to date)
            pos = self.dev.get_pos(timeout=0)[:3]
            self._lastUpdate = ptime.time()
            if self._lastPos is not None:
                dif = np.linalg.norm(np.array(pos, dtype=float) - np.array(self._lastPos, dtype=float))

            # do not report changes < 100 nm
            if self._lastPos is None or dif > 0.1:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos

    def _positionChanged(self, dev, newPos, oldPos):
        # called by driver poller when position has changed
        now = ptime.time()
        # rate limit updates to 10 Hz
        wait = 100e-3 - (now - self._lastUpdate)
        if wait > 0:
            self._sigRestartUpdateTimer.emit(wait)
        else:
            self._getPosition()

    def _restartUpdateTimer(self, wait):
        self._updateTimer.start(int(wait * 1000))

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def quit(self):
        Sensapex.devices.pop(self.devid, None)
        if len(Sensapex.devices) == 0:
            UMP.get_ump().poller.stop()
        Stage.quit(self)

    def _move(self, pos, speed, linear):
        with self.lock:
            speed = self._interpretSpeed(speed)
            self._lastMove = SensapexMoveFuture(self, pos, speed, self._force_linear_movement or linear)
            return self._lastMove

    def deviceInterface(self, win):
        return SensapexInterface(self, win)


class SensapexMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Sensapex manipulator.
    """
    def __init__(self, dev, pos, speed, linear):
        MoveFuture.__init__(self, dev, pos, speed)

        # limit the speed so that no move is expected to take less than 200 ms
        # (otherwise we get big move errors with uMp)
        minimumMoveTime = 0.2
        distance = np.linalg.norm(self.startPos - self.targetPos)
        if speed > 10e-6:
            self.speed = min(speed, distance / minimumMoveTime)

        self._linear = linear
        self._interrupted = False
        self._errorMsg = None
        self._checked = False

        # no move requested; just bail early
        if distance == 0:
            self._taskDone(interrupted=False)
            return

        if self.speed >= 1e-6:
            assert linear
            self._moveReq = self.dev.dev.goto_pos(pos, self.speed * 1e6, simultaneous=linear, linear=linear)
            self._monitorThread = threading.Thread(target=self._watchForFinish, daemon=True)
        else:
            # uMp has trouble with very slow speeds, so we do this manually by looping over small steps
            self._moveReq = None
            self._monitorThread = threading.Thread(target=self._stepwiseMove, daemon=True)
        self._monitorThread.start()

    def _watchForFinish(self):
        moveReq = self._moveReq
        moveReq.finished_event.wait()
        self._taskDone(
            interrupted=moveReq.interrupted,
            error=self._generateErrorMessage(),
            state=None,
            excInfo=None,
        )

    def _stepwiseMove(self):
        speed = self.speed * 1e6
        delta = (self.targetPos - self.startPos)
        distance = np.linalg.norm(delta)
        duration = distance / speed
        lastTarget = self.startPos
        print(f"stepwise speed: {speed}  delta: {delta}  distance: {distance}  duration: {duration}")
        while True:
            # where should be be at this point?
            elapsedTime = ptime.time() - self.startTime
            fractionComplete = min(1.0, elapsedTime / duration)
            currentTarget = self.startPos + delta * fractionComplete

            # rate-limit move requests
            minStepUm = 0.5
            distanceToMove = np.linalg.norm(currentTarget - lastTarget)
            if distanceToMove < minStepUm:
                time.sleep((minStepUm - distanceToMove) / speed)
                continue

            # request the next step and wait
            lastTarget = currentTarget
            self._moveReq = self.dev.dev.goto_pos(currentTarget, speed=1.0, simultaneous=True, linear=True)
            while not self._moveReq.finished_event.wait(0.2):
                if self._stopRequested:
                    self._moveReq.interrupt(reason=self._errorMessage)
                if self._moveReq.interrupted:
                    break

            if fractionComplete == 1.0 or self._moveReq.interrupted:
                break

        self._taskDone(
            interrupted=self._moveReq.interrupted or self._stopRequested,
            error=self._generateErrorMessage(),
            state=None,
            excInfo=None,
        )

    def _generateErrorMessage(self):
        # interrupted?
        if self._moveReq.interrupted:
            return self._moveReq.interrupt_reason
        else:
            # did we reach target?
            pos = self._moveReq.last_pos
            dif = np.linalg.norm(np.array(pos) - np.array(self.targetPos))
            if dif > self.dev.maxMoveError * 1e6:  # require 1um accuracy
                # missed
                return "{} stopped before reaching target (start={}, target={}, position={}, dif={}, speed={}).".format(
                    self.dev.name(), self.startPos, self.targetPos, pos, dif, self.speed
                )

        return None


class SensapexInterface(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.axCtrls = {}
        self.posLabels = {}

        self.positionLabelWidget = Qt.QWidget()
        self.layout.addWidget(self.positionLabelWidget, 0, 0)
        self.positionLabelLayout = Qt.QGridLayout()
        self.positionLabelWidget.setLayout(self.positionLabelLayout)
        self.positionLabelLayout.setContentsMargins(0, 0, 0, 0)

        self.globalLabel = Qt.QLabel("global")
        self.positionLabelLayout.addWidget(self.globalLabel, 0, 1)
        self.stageLabel = Qt.QLabel("stage")
        self.positionLabelLayout.addWidget(self.stageLabel, 0, 2)

        self.btnContainer = Qt.QWidget()
        self.btnLayout = Qt.QGridLayout()
        self.btnContainer.setLayout(self.btnLayout)
        self.layout.addWidget(self.btnContainer, self.layout.rowCount(), 0)
        self.btnLayout.setContentsMargins(0, 0, 0, 0)

        self.goHomeBtn = Qt.QPushButton("Home")
        self.btnLayout.addWidget(self.goHomeBtn, 0, 0)
        self.goHomeBtn.clicked.connect(self.goHomeClicked)

        self.setHomeBtn = Qt.QPushButton("Set Home")
        self.btnLayout.addWidget(self.setHomeBtn, 0, 1)
        self.setHomeBtn.clicked.connect(self.setHomeClicked)

        self.calibrateBtn = Qt.QPushButton("Calibrate")
        self.btnLayout.addWidget(self.calibrateBtn, 0, 2)
        self.calibrateBtn.clicked.connect(self.calibrateClicked)

        self.stopBtn = Qt.QPushButton("Stop!")
        self.btnLayout.addWidget(self.stopBtn, 1, 0)
        self.stopBtn.clicked.connect(self.stopClicked)
        self.stopBtn.setStyleSheet("QPushButton {background-color:red; color:white}")

        self.calibrateZeroBtn = Qt.QPushButton("Run Zero Calibration")
        self.btnLayout.addWidget(self.calibrateZeroBtn, 1, 1)
        self.calibrateZeroBtn.clicked.connect(self.calibrateZeroClicked)

        self.calibrateLoadBtn = Qt.QPushButton("Run Load Calibration")
        self.btnLayout.addWidget(self.calibrateLoadBtn, 1, 2)
        self.calibrateLoadBtn.clicked.connect(self.calibrateLoadClicked)

        self.softStartValue = Qt.QLineEdit()

        self.btnLayout.addWidget(self.softStartValue, 2, 1)
        self.softStartValue.editingFinished.connect(self.softstartChanged)
        self.getSoftStartValue()

        self.softStartBtn = Qt.QPushButton("Soft Start Enabled")
        self.softStartBtn.setCheckable(True)
        self.softStartBtn.setStyleSheet("QPushButton:checked{background-color:lightgreen; color:black}")
        self.btnLayout.addWidget(self.softStartBtn, 2, 0)
        self.softStartBtn.clicked.connect(self.softstartClicked)
        self.getSoftStartState()

        self.calibrateWindow = None

        cap = dev.capabilities()
        for axis, axisName in enumerate(self.dev.axes()):
            if cap["getPos"][axis]:
                axLabel = Qt.QLabel(axisName)
                axLabel.setMaximumWidth(15)
                globalPosLabel = Qt.QLabel("0")
                stagePosLabel = Qt.QLabel("0")
                self.posLabels[axis] = (globalPosLabel, stagePosLabel)
                widgets = [axLabel, globalPosLabel, stagePosLabel]
                if cap["limits"][axis]:
                    minCheck = Qt.QCheckBox("Min:")
                    minCheck.tag = (axis, 0)
                    maxCheck = Qt.QCheckBox("Max:")
                    maxCheck.tag = (axis, 1)
                    self.limitChecks[axis] = (minCheck, maxCheck)
                    widgets.extend([minCheck, maxCheck])
                    for check in (minCheck, maxCheck):
                        check.clicked.connect(self.limitCheckClicked)

                nextRow = self.positionLabelLayout.rowCount()
                for i, w in enumerate(widgets):
                    self.positionLabelLayout.addWidget(w, nextRow, i)
                self.axCtrls[axis] = widgets
        self.dev.sigPositionChanged.connect(self.update)

        self.update()

    def update(self):
        globalPos = self.dev.globalPosition()
        stagePos = self.dev.getPosition()
        for i in self.posLabels:
            text = pg.siFormat(globalPos[i], suffix="m", precision=5)
            self.posLabels[i][0].setText(text)
            self.posLabels[i][1].setText(str(stagePos[i]))

    def goHomeClicked(self):
        self.dev.goHome()

    def setHomeClicked(self):
        self.dev.setHomePosition()

    def calibrateClicked(self):
        if self.calibrateWindow is None:
            if self.dev.isManipulator:
                self.calibrateWindow = ManipulatorAxesCalibrationWindow(self.dev)
            else:
                self.calibrateWindow = StageAxesCalibrationWindow(self.dev)
        self.calibrateWindow.show()
        self.calibrateWindow.raise_()

    def calibrateZeroClicked(self):
        self.dev.dev.calibrate_zero_position()

    def calibrateLoadClicked(self):
        self.dev.dev.calibrate_load()

    def stopClicked(self):
        self.dev.dev.stop()

    def getSoftStartState(self):
        state = self.dev.dev.get_soft_start_state()

        if state == 1:
            self.softStartBtn.setChecked(True)
            self.softStartBtn.setText("Soft Start Enabled")
            self.softStartValue.setVisible(True)
            self.getSoftStartValue()
            return True

        self.softStartBtn.setChecked(False)
        self.softStartBtn.setText("Soft Start Disabled")
        self.softStartValue.setVisible(False)
        return False

    def softstartClicked(self):
        checked = self.getSoftStartState()
        if checked:
            self.dev.dev.set_soft_start_state(0)
        else:
            self.dev.dev.set_soft_start_state(1)

        self.getSoftStartState()

    def softstartChanged(self):
        value = int(self.softStartValue.text())
        self.dev.dev.set_soft_start_value(value)

    def getSoftStartValue(self):
        value = self.dev.dev.get_soft_start_value()
        self.softStartValue.setText(str(value))
