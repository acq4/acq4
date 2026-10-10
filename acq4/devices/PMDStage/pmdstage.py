from __future__ import annotations

import threading

from acq4.drivers.pmdmotion import MagellanPMD
from acq4.drivers.pmdmotion.protocol import ProfileMode
from acq4.drivers.stage import MoveCancelled, MoveStopped
from acq4.util import Qt
from acq4.util.task import FutureButton, ManualQtFriendlyTask, Stopped
from ..Stage import MoveFuture, Stage, StageInterface

#: Required config key -> MagellanPMD argument, for values in SI units (converted to mm).
REQUIRED_SI_KEYS = {
    'acceleration': 'acceleration',
    'jerk': 'jerk',
    'homingSpeed': 'homing_speed',
    'homingAcceleration': 'homing_acceleration',
    'homingJerk': 'homing_jerk',
    'homeOffset': 'home_offset',
    'homeSweep': 'home_sweep',
}

#: Optional config key -> (MagellanPMD argument, default), distances in m (converted to mm).
#: A None default leaves the driver's default, in encoder counts.
OPTIONAL_DISTANCE_KEYS = {
    'arrivalWindow': ('arrival_window', 5e-6),
    'positionChangeThreshold': ('position_change_threshold', 250e-9),
    'positionLimit': ('position_limit', None),
    'motionThreshold': ('motion_threshold', None),
    'settleThreshold': ('settle_threshold', None),
    'homeSettleThreshold': ('home_settle_threshold', None),
}


class PMDStage(Stage):
    """A stage of PMD Magellan single-axis controllers driven over their serial protocol.

    Device coordinates are mm (the driver is built with ``counts_per_unit`` counts per
    mm), so ``scale`` defaults to 1e-3 per axis. Speeds cross the Stage API in m/s and
    are multiplied by 1e3 for the driver.

    Creating the device connects but never commutates. Once the GUI event loop runs after
    construction, :meth:`commutate` is called for any unphased axes; it asks first unless
    ``autoCommutate``, and a failure is raised into ACQ4's exception handler. Unphased
    axes refuse to move until commutation succeeds. Homing moves the stage a long way
    and cannot be interrupted; the device dock asks for confirmation first.

    Config options::

        axes : dict
            Required. Axis name -> controller node ID on the RS-485 bus, e.g. ``{'x': 1}``.
        counts_per_unit : float
            Required. Encoder counts per mm.
        acceleration : float
            Required. Acceleration (m/s²) programmed for every move.
        jerk : float
            Required. Jerk (m/s³) for S-curve moves.
        homingSpeed, homingAcceleration, homingJerk : float
            Required. S-curve profile (m/s, m/s², m/s³) for homing moves.
        homeOffset : float
            Required. Distance (m) backed off past the home flag before the final approach.
        homeSweep : float
            Required. Longest homing sweep (m); at least the axis travel.
        autoCommutate : bool
            Commutate without asking for confirmation. Default False.
        motionSynergyPath : str
            MotionSynergy folder whose ``SupportFolder/Instrument.cfg`` names the serial
            port; used for port discovery when ``port`` is None.
        port : str | None
            Serial port override. Default None (discover).
        baudrate : int
            Default 57600.
        poll_interval : float
            Seconds between position polls. Default 0.025.
        positionChangeThreshold : float
            Movement (m) on any axis needed to report a new position. Default 250 nm.
        profile : str
            'trapezoidal' (default) or 'scurve'.
        arrivalWindow : float
            Distance (m) from target within which a stopped axis counts as arrived. Default 5 µm.
        positionLimit : float
            Position reads (m) of larger magnitude are discarded. Default 2**27 counts.
        motionThreshold : float
            Movement (m) from the start that proves a trajectory ran. Default 100 counts.
        settleThreshold, homeSettleThreshold : float
            An axis is at rest once it moves less than this (m) in a short hold time,
            after phase initialization and at the home flag. Defaults 100 and 10 counts.

    See ``config/example/devices.cfg`` for an example.
    """

    #: Emitted with the list of unphased axes whenever it may have changed.
    sigPhasingChanged = Qt.Signal(object)

    #: Emitted with ``(action, exception or None)`` when a commutate/home finishes.
    sigActionFinished = Qt.Signal(object, object)

    # exception from the commutation started after construction
    _sigStartupCommutationFailed = Qt.Signal(object)

    driverClass = MagellanPMD

    def __init__(self, man, config: dict, name):
        if not config.get('axes'):
            raise KeyError("PMDStage config is missing required key: axes")
        self._axes = tuple(config['axes'])
        config.setdefault('scale', (1e-3,) * len(self._axes))
        self._activeAction = None  # (name, task) of a running commutate/home
        self._closed = False

        self.driver = self._makeDriver(config)
        self.driver.connect()
        try:
            # trapezoidal moves retarget in flight; S-curve moves stop first
            self.canRetargetInFlight = self.driver.default_profile == ProfileMode.TRAPEZOIDAL
            Stage.__init__(self, man, config, name)
            self.posChanged(self._getPosition())
            self.driver.set_position_callback(self._driverPositionChanged)
        except Exception:
            self.driver.close()
            raise
        self._sigStartupCommutationFailed.connect(self._raiseStartupCommutationError)
        Qt.QTimer.singleShot(0, self._commutateAfterStartup)

    def _makeDriver(self, config):
        missing = [k for k in ('counts_per_unit', *REQUIRED_SI_KEYS) if config.get(k) is None]
        if missing:
            raise KeyError(f"PMDStage config is missing required keys: {', '.join(missing)}")
        kwds = {arg: config[key] * 1e3 for key, arg in REQUIRED_SI_KEYS.items()}
        for key, (arg, default) in OPTIONAL_DISTANCE_KEYS.items():
            value = config.get(key, default)
            if value is not None:
                kwds[arg] = value * 1e3
        for key in ('profile', 'baudrate', 'poll_interval'):
            if config.get(key) is not None:
                kwds[key] = config[key]
        return self.driverClass(
            dict(config['axes']),
            port=config.get('port'),
            motion_synergy_path=config.get('motionSynergyPath'),
            counts_per_unit=config['counts_per_unit'],
            auto_commutate=bool(config.get('autoCommutate', False)),
            **kwds,
        )

    def axes(self):
        return self._axes

    def capabilities(self):
        if 'capabilities' in self.config:
            return self.config['capabilities']
        n = len(self._axes)
        return {'getPos': (True,) * n, 'setPos': (True,) * n, 'limits': (False,) * n}

    @property
    def acceleration(self) -> float:
        """Acceleration (m/s²) the driver programs, converted from mm/s²."""
        return self.driver.default_acceleration * 1e-3

    @property
    def positionUpdatesPerSecond(self):
        """Nominal position poll rate (Hz)."""
        return 1.0 / self.driver.poll_interval

    # ---- position ----

    def _posFromDriver(self, pos: dict) -> list:
        """Axis dict (mm) -> list in axis order; axes missing from *pos* keep their last value."""
        last = self._lastPos
        return [float(pos[ax]) if ax in pos else last[i] for i, ax in enumerate(self._axes)]

    def _driverPositionChanged(self, pos):
        # runs on the driver's control thread
        self.posChanged(self._posFromDriver(pos))

    def _getPosition(self):
        return self._posFromDriver(self.driver.get_position() or {})

    # ---- motion ----

    def unphasedAxes(self) -> list:
        """Axes that need commutation before they can move."""
        return self.driver.unphased_axes()

    def _move(self, pos, speed, linear, name=None, **kwds):
        """Start a move to *pos* (mm; None = stay) at *speed* (m/s or 'fast'/'slow').

        *linear* is ignored: multi-axis moves are always straight lines. The move fails
        (RequestFailed, cause NotCommutatedError) if it includes an unphased axis.
        """
        action = self._activeAction
        if action is not None:
            raise RuntimeError(f"{self.name()}: cannot move while {action[0]} is running")
        speed = self._interpretSpeed(speed)
        self._lastMove = PMDMoveFuture(self, list(pos), speed, name=name, **kwds)
        return self._lastMove

    def stop(self, reason=None):
        """Stop all axes; the active move completes as stopped."""
        return self.driver.stop(reason or 'stop requested')

    # ---- commutation and homing ----

    def commutate(self, axes=None, confirm=None) -> ManualQtFriendlyTask:
        """Commutate the unphased axes among *axes* (default all); returns a task.

        See ``MagellanPMD.commutate``: resolves at once if no axis needs it; asks first if
        *confirm* (None = unless ``autoCommutate``), and declining stops the task; on
        failure ``task.wait()`` raises RequestFailed caused by CommutationError. MOVES each
        axis a large, unpredictable distance and cannot be interrupted. Blocks while asking.
        """
        return self._runAction('commutation', self.driver.commutate, axes, confirm=confirm)

    def _commutateAfterStartup(self):
        """Commutate unphased axes once the device exists (GUI thread); silent if none."""
        if self._closed or not self.unphasedAxes():
            return
        self.commutate().add_finish_callback(self._startupCommutationFinished)

    def _startupCommutationFinished(self, result, exc):
        # any thread; Stopped = declined, already logged by _runAction
        if exc is not None and not isinstance(exc, Stopped):
            self._sigStartupCommutationFailed.emit(exc)

    def _raiseStartupCommutationError(self, exc):
        raise RuntimeError(f"{self.name()}: commutation after startup failed: {exc}") from exc

    def home(self, axes=None) -> ManualQtFriendlyTask:
        """Home *axes* (default all) on the centre vane, zeroing their position.

        Sweeps up to the full travel and cannot be interrupted. Axes must be commutated.
        """
        return self._runAction('homing', self.driver.home, axes)

    def homingWarning(self, axes) -> str:
        """Confirmation text for homing *axes*."""
        names = ', '.join(ax.upper() for ax in axes)
        return (
            f"Home {self.name()} axes {names}?\n\n"
            f"Homing sweeps each axis up to its full travel to find its home flag, then resets "
            f"its zero position there. It CANNOT BE INTERRUPTED once started. Make sure the full "
            f"range of motion of every axis is clear."
        )

    def _runAction(self, action, driverCall, axes, **kwds) -> ManualQtFriendlyTask:
        """Run a driver commutate/home call; the task resolves, stops or fails with the request."""
        axes = None if axes is None else list(axes)
        task = ManualQtFriendlyTask(name=f"{self.name()} {action}")
        if self._activeAction is not None:
            raise RuntimeError(f"{self.name()}: {self._activeAction[0]} is already running")
        self._activeAction = (action, task)
        try:
            self.logger.info(f"{self.name()}: starting {action} of axes {axes or 'all'}")
            request = driverCall(axes=axes, **kwds)
        except Exception:
            self._activeAction = None
            raise

        def waitForRequest():
            exc = None
            try:
                result = request.wait(timeout=None)
            except MoveCancelled as e:
                self._activeAction = None
                self.logger.info(f"{self.name()}: {action} cancelled: {e}")
                task.stop(str(e))
                return
            except Exception as e:
                exc = e
            finally:
                self._activeAction = None
            if exc is None:
                self.logger.info(f"{self.name()}: {action} finished")
                task.resolve(result)
            else:
                self.logger.error(f"{self.name()}: {action} failed: {exc}")
                task.fail(exc)
            self.sigPhasingChanged.emit(self.unphasedAxes())
            self.sigActionFinished.emit(action, exc)

        threading.Thread(target=waitForRequest, daemon=True, name=f"{self.name()} {action}").start()
        return task

    def isBusy(self) -> bool:
        """Whether a commutate or home is running."""
        return self._activeAction is not None

    # ---- lifecycle ----

    def deviceInterface(self, win):
        return PMDStageInterface(self, win)

    def quit(self):
        self._closed = True
        # _teardown() rather than Stage.quit(): stop() must run before the driver closes.
        Stage._teardown(self)
        self.driver.set_position_callback(None)
        try:
            self.driver.stop('device quit').wait(timeout=2.0)
        except Exception:
            self.logger.exception(f"{self.name()}: stop on quit failed")
        self.driver.close()


class PMDMoveFuture(MoveFuture):
    """A move in progress on a :class:`PMDStage`.

    *pos*, :attr:`startPos` and :attr:`targetPos` are mm; :attr:`speed` is m/s. Completes
    with ``Stopped`` when the driver reports the move stopped or cancelled, and fails
    with :class:`~acq4.drivers.stage.MoveInterrupted` when another move superseded it,
    or with :class:`~acq4.drivers.stage.RequestFailed` (carrying the reason) on error.
    Extra keyword arguments (acceleration, jerk, profile) go to ``MagellanPMD.move_to``.
    """

    def __init__(self, dev: PMDStage, pos, speed, name=None, **kwds):
        current = dev.getPosition()
        target = {ax: float(v) for ax, v in zip(dev.axes(), pos) if v is not None}
        fullPos = [current[i] if v is None else v for i, v in enumerate(pos)]
        MoveFuture.__init__(self, dev, fullPos, speed, name=name)
        self.request = dev.driver.move_to(target, speed * 1e3, reason=self._name, **kwds)
        self.producerThread(self._waitForRequest, name=f"{self._name} monitor").start()

    def _waitForRequest(self):
        try:
            self.request.wait(timeout=None)
        except MoveStopped as exc:  # includes MoveCancelled
            if not self.is_done:
                # base-class stop: completes with Stopped without stopping the device again
                ManualQtFriendlyTask.stop(self, str(exc))
            return
        except Exception as exc:  # MoveInterrupted, RequestFailed
            if not self.is_stopped:
                self.fail(exc)
            return
        if not self.is_stopped:
            self.resolve(None)


class PMDStageInterface(StageInterface):
    """Stage dock with commutation/homing status and buttons."""

    def __init__(self, dev: PMDStage, win):
        StageInterface.__init__(self, dev, win)
        group = Qt.QGroupBox("Commutation / homing")
        layout = Qt.QGridLayout()
        group.setLayout(layout)
        self.layout.addWidget(group, self.layout.rowCount(), 0)

        self.phaseLabel = Qt.QLabel('')
        self.phaseLabel.setWordWrap(True)
        layout.addWidget(self.phaseLabel, 0, 0, 1, 2)
        self.commutateBtn = FutureButton(
            self.commutateClicked, 'Commutate', stoppable=False, raiseOnError=False,
            processing='Commutating...',
        )
        self.commutateBtn.setToolTip(
            "Phase-initialize the motors. May move each axis a large, unpredictable distance; "
            "cannot be interrupted."
        )
        layout.addWidget(self.commutateBtn, 1, 0)
        self.homeBtn = FutureButton(
            self.homeClicked, 'Home axes', stoppable=False, raiseOnError=False,
            processing='Homing...',
        )
        self.homeBtn.setToolTip("Find the centre flag on each axis and zero there. Sweeps the full travel.")
        layout.addWidget(self.homeBtn, 1, 1)

        for btn in (self.commutateBtn, self.homeBtn):
            # FutureButton.reset() after a Stopped task leaves a non-stoppable button disabled
            btn.sigFinished.connect(lambda task, btn=btn: btn.setEnabled(True))

        dev.sigPhasingChanged.connect(self.updatePhasing)
        dev.sigActionFinished.connect(self.actionFinished)
        self.updatePhasing(dev.unphasedAxes())

    def updatePhasing(self, unphased):
        if unphased:
            self.phaseLabel.setText(
                f"Not commutated: {', '.join(ax.upper() for ax in unphased)} (cannot move)"
            )
            self.phaseLabel.setStyleSheet("color: #C00; font-weight: bold;")
        else:
            self.phaseLabel.setText("All axes commutated")
            self.phaseLabel.setStyleSheet("")

    def confirm(self, title, text) -> bool:
        """Ask the user to confirm; tests override this."""
        response = Qt.QMessageBox.warning(
            self, title, text, Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel, Qt.QMessageBox.Cancel
        )
        return response == Qt.QMessageBox.Ok

    def _declined(self, action):
        task = ManualQtFriendlyTask(name=f"{self.dev.name()} {action}")
        task.stop("cancelled by user")
        return task

    def commutateClicked(self):
        return self.dev.commutate(self.dev.unphasedAxes() or None)

    def homeClicked(self):
        axes = list(self.dev.axes())
        if not self.confirm("Home stage", self.dev.homingWarning(axes)):
            return self._declined('homing')
        return self.dev.home(axes)

    def actionFinished(self, action, exc):
        if exc is not None:
            self.showMessage(f"{self.dev.name()} {action} failed", f"{action.capitalize()} failed:\n\n{exc}")

    def showMessage(self, title, text):
        """Show an error/notice box; tests override this."""
        Qt.QMessageBox.critical(self, title, text)
