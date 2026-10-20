from __future__ import annotations

import threading

from acq4.drivers.pmdmotion import MagellanPMD
from acq4.drivers.pmdmotion.backend import profile_mode
from acq4.drivers.pmdmotion.protocol import ProfileMode
from acq4.drivers.stage import MoveCancelled, MoveStopped
from acq4.util import Qt
from acq4.util.task import FutureButton, ManualQtFriendlyTask, Stopped
from ..ControlSurface import UnsupportedControlFeature
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

DEFAULT_POLL_INTERVAL = 0.025

#: Seconds construction waits for the first complete position read before failing.
FIRST_POSITION_TIMEOUT = 5.0

#: Seconds ``getPosition(refresh=True)`` waits for its read to reach the controller.
POSITION_READ_TIMEOUT = 5.0


class PMDStage(Stage):
    """A stage of PMD Magellan single-axis controllers driven over their serial protocol.

    Device coordinates are mm (the driver is built with ``counts_per_unit`` counts per
    mm), so ``scale`` defaults to 1e-3 per axis. Speeds cross the Stage API in m/s and
    are multiplied by 1e3 for the driver.

    Construction fails unless every axis reports a valid position within
    ``FIRST_POSITION_TIMEOUT`` seconds of connecting.

    Creating the device connects but never commutates. Commutation runs only once, when the
    GUI event loop first runs after construction: the driver commutates the unphased axes
    (unphased after a power cycle), asking first unless ``autoCommutate``; a failure is
    raised into ACQ4's exception handler. If every axis is phased this logs nothing above
    debug level. Unphased axes refuse to move until a restart commutates them. Homing moves
    the stage a long way and cannot be interrupted; the device dock asks for confirmation first.

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
        setRs485_4w : bool
            Set the port's Moxa registry SerInterface to RS-485-4W at connect (UAC prompt if
            it must change). Connecting fails if the adapter cannot be put in 4-wire mode;
            only turn it on for a port whose driver has that setting. Default False.
        port : str | None
            Serial port. Exactly one of ``port`` and ``portSearch`` is required.
        portSearch : str | None
            Finds the port: ``'VID:PID'`` (hex, e.g. ``'0403:6010'``) or text in the port
            description (e.g. ``'moxa'``). Must match exactly one attached port.
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

        controls : dict
            Control-surface bindings, as documented on
            :class:`~acq4.devices.Stage.Stage.Stage`. Also accepts axis-enable toggle buttons
            ``enableX``, ``enableY``, ``enableZ`` (axis letters as configured) and ``enableXY``.
            A press enables the axes it covers, or disables them if all are enabled; the label
            is drawn green while enabled, red while disabled, amber with a ``!`` if mixed.
            ``enableXY`` cannot be bound together with ``enableX`` or ``enableY``.

    See ``config/example/devices.cfg`` for an example.
    """

    #: Emitted with ``(action, exception or None)`` when startup commutation or homing finishes.
    sigActionFinished = Qt.Signal(object, object)

    # exception from the commutation started after construction
    _sigStartupCommutationFailed = Qt.Signal(object)

    #: Internal: carries the per-axis enabled-state tuple from a worker thread to the GUI thread.
    _sigAxisEnabledChanged = Qt.Signal(object)

    #: Background colours of an axis-enable toggle: all axes enabled, all disabled, mixed.
    AXIS_ENABLED_COLOR = (40, 167, 69)
    AXIS_DISABLED_COLOR = (180, 30, 30)
    AXIS_MIXED_COLOR = (255, 170, 0)

    #: Appended to the label of a multi-axis toggle whose axes disagree, e.g. ``'XY!'``.
    AXIS_MIXED_SUFFIX = '!'

    driverClass = MagellanPMD

    def __init__(self, man, config: dict, name):
        if not config.get('axes'):
            raise KeyError("PMDStage config is missing required key: axes")
        self._axes = tuple(config['axes'])
        config.setdefault('scale', (1e-3,) * len(self._axes))
        self._activeAction = None  # (name, task) of running startup commutation or homing
        # held across the check and the start in _runAction and _move, so "one action at a
        # time" and "do not move while homing" cannot both be satisfied by two threads at once
        self._actionLock = threading.Lock()
        self._closed = False
        # set before Stage.__init__, whose bindControl() fills them
        self._axisEnableControls = {}  # tuple of axis indices -> Control
        self._axisEnablePainters = {}  # tuple of axis indices -> callable(label, color)

        self._firstPosition = threading.Event()
        self.driver = self._makeDriver(config)
        self.driver.connect()
        try:
            # Trapezoidal moves retarget in flight, ~90 ms per superseding move on the bus.
            # S-curve moves stop first; their retarget interval has not been measured.
            if profile_mode(config.get('profile') or 'trapezoidal') == ProfileMode.TRAPEZOIDAL:
                self.retargetInterval = 0.1
            elif 'retargetInterval' not in config:
                raise NotImplementedError(
                    f"{name}: retargetInterval for S-curve profiles is unmeasured; "
                    f"set 'retargetInterval' in the config")
            Stage.__init__(self, man, config, name)
            self.driver.set_position_callback(self._driverPositionChanged)
            if not self._firstPosition.wait(FIRST_POSITION_TIMEOUT):
                raise RuntimeError(
                    f"{name}: no valid position read from every axis within {FIRST_POSITION_TIMEOUT} s")
        except Exception:
            self.driver.close()
            raise
        self._sigStartupCommutationFailed.connect(self._raiseStartupCommutationError)
        self._sigAxisEnabledChanged.connect(self._paintAxisEnableControls, Qt.Qt.QueuedConnection)
        self.sigActionFinished.connect(lambda *args: self._refreshAxisEnabled())
        self._refreshAxisEnabled()
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
        for key in ('profile', 'baudrate'):
            if config.get(key) is not None:
                kwds[key] = config[key]
        return self.driverClass(
            dict(config['axes']),
            port=config.get('port'),
            port_search=config.get('portSearch'),
            counts_per_unit=config['counts_per_unit'],
            poll_interval=self._pollInterval(config),
            set_rs485_4w=bool(config.get('setRs485_4w', False)),
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

    @staticmethod
    def _pollInterval(config) -> float:
        value = config.get('poll_interval')
        return DEFAULT_POLL_INTERVAL if value is None else value

    @property
    def acceleration(self) -> float:
        """Acceleration (m/s²) programmed for every move, from the config."""
        return self.config['acceleration']

    @property
    def positionUpdatesPerSecond(self):
        """Nominal position poll rate (Hz)."""
        return 1.0 / self._pollInterval(self.config)

    # ---- position ----

    def _posFromDriver(self, pos: dict) -> list:
        """Axis dict (mm) -> list in axis order; RuntimeError if any axis is missing."""
        missing = [ax for ax in self._axes if ax not in pos]
        if missing:
            raise RuntimeError(f"{self.name()}: no position for axes {missing}")
        return [float(pos[ax]) for ax in self._axes]

    def _driverPositionChanged(self, pos):
        # runs on the driver's control thread
        self.posChanged(self._posFromDriver(pos))
        self._firstPosition.set()

    def positionReport(self):
        """The published position with its age and whether a position read has failed since.

        A :class:`~acq4.drivers.stage.PositionReport`, or None before the first read. What
        :meth:`getPosition` returns without a refresh is this report's position, which a
        stage whose link has dropped goes on answering with indefinitely; ``stale`` and
        ``age()`` are how a caller tells. While it is stale the stage refuses to move.
        """
        return self.driver.position_report()

    def _getPosition(self):
        """Read every axis from the controller and return the position in axis order.

        Blocks on the bus, and waits behind whatever the control thread is already doing,
        so a device operation that holds it (homing) delays this by its whole duration and
        then fails with TimeoutError. The read also republishes the position.
        """
        return self._posFromDriver(self.driver.read_position().wait(POSITION_READ_TIMEOUT))

    # ---- motion ----

    def _move(self, pos, speed, linear, name=None, **kwds):
        """Start a move to *pos* (mm; None = stay) at *speed* (m/s or 'fast'/'slow').

        *linear* is ignored: multi-axis moves are always straight lines. The move fails
        (RequestFailed, cause NotCommutatedError) if it includes an unphased axis.
        """
        with self._actionLock:
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

    def _commutateAfterStartup(self):
        """Commutate the unphased axes via ``MagellanPMD.commutate``; the only commutation path (GUI thread)."""
        if self._closed:
            return
        task = self._runAction('commutation', self.driver.commutate, None, quiet=_nothingCommutated)
        task.add_finish_callback(self._startupCommutationFinished)

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

    def _runAction(self, action, driverCall, axes, quiet=None, **kwds) -> ManualQtFriendlyTask:
        """Run a driver commutate/home call; the task resolves, stops or fails with the request.

        With *quiet*, the start is not logged, and a success for which ``quiet(result)`` is
        true is logged at debug level.
        """
        axes = None if axes is None else list(axes)
        task = ManualQtFriendlyTask(name=f"{self.name()} {action}")
        with self._actionLock:
            if self._activeAction is not None:
                raise RuntimeError(f"{self.name()}: {self._activeAction[0]} is already running")
            self._activeAction = (action, task)
            try:
                if quiet is None:
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
                log = self.logger.debug if quiet is not None and quiet(result) else self.logger.info
                log(f"{self.name()}: {action} finished: {result}")
                task.resolve(result)
            else:
                self.logger.error(f"{self.name()}: {action} failed: {exc}")
                task.fail(exc)
            self.sigActionFinished.emit(action, exc)

        threading.Thread(target=waitForRequest, daemon=True, name=f"{self.name()} {action}").start()
        return task

    def isBusy(self) -> bool:
        """Whether startup commutation or homing is running."""
        return self._activeAction is not None

    # ---- axis-enable toggle controls ----

    def controlNames(self) -> list:
        return list(Stage.controlNames(self)) + [
            self._axisEnableName(axes) for axes in self._axisEnableGroups()
        ]

    def bindControl(self, name, control, conf):
        for axes in self._axisEnableGroups():
            if name == self._axisEnableName(axes):
                self._bindAxisEnable(name, axes, control)
                return
        Stage.bindControl(self, name, control, conf)

    def _axisEnableGroups(self) -> list:
        """Axis groups an enable toggle can cover, as tuples of axis indices: each axis, plus x and y together."""
        groups = [(i,) for i in range(len(self._axes))]
        if 'x' in self._axes and 'y' in self._axes:
            groups.append((self._axes.index('x'), self._axes.index('y')))
        return groups

    def _axisEnableLabel(self, axes) -> str:
        """Upper-case axis letters of *axes* in axis order, e.g. ``'XY'``."""
        return ''.join(str(self._axes[i]) for i in axes).upper()

    def _axisEnableName(self, axes) -> str:
        return f'enable{self._axisEnableLabel(axes)}'

    def _bindAxisEnable(self, name, axes, control):
        """Bind *control* as the enable toggle for axis indices *axes*.

        Raises ValueError if an already bound toggle shares an axis (e.g. ``enableX`` with ``enableXY``).
        """
        for bound in self._axisEnableControls:
            if set(axes) & set(bound):
                raise ValueError(
                    f"{self.name()}: control {name!r} overlaps {self._axisEnableName(bound)!r}; "
                    f"bind one or the other, not both."
                )
        self._axisEnableControls[axes] = control
        control.sigPressed.connect(self._axisEnablePressed)
        self._bindAxisEnableIndicator(axes, control)

    def _bindAxisEnableIndicator(self, axes, control):
        """Choose how *control* draws toggle state: label plus colour if it can, else colour alone, else nothing."""
        label = self._axisEnableLabel(axes)
        candidates = []
        if hasattr(control, 'setText') and control.capabilities()['output'].get('text'):
            candidates.append(lambda text, color: control.setText(text, background=color))
        if hasattr(control, 'setColor'):
            candidates.append(lambda text, color: control.setColor(color))
        for painter in candidates:
            try:
                painter(label, self.AXIS_DISABLED_COLOR)
            except UnsupportedControlFeature:
                continue
            self._axisEnablePainters[axes] = painter
            return
        self.logger.warning(f"{self.name()}: {control} cannot indicate the state of {label!r}; the toggle still works.")

    def _axisEnablePressed(self, control):
        for axes, ctl in self._axisEnableControls.items():
            if ctl is control:
                self._toggleAxes(axes)
                return

    def _toggleAxes(self, axes):
        """Disable *axes* if all are enabled, otherwise enable them, then repaint from the driver's state."""
        names = [self._axes[i] for i in axes]
        target = not all(self.driver.is_enabled()[ax] for ax in names)
        request = self.driver.set_enabled(target, names, reason='axis-enable toggle')

        def finish():
            try:
                request.wait(timeout=None)
            except Exception:
                self.logger.exception(f"{self.name()}: failed to {'enable' if target else 'disable'} axes {names}")
            self._refreshAxisEnabled()

        threading.Thread(target=finish, daemon=True, name=f"{self.name()} axis enable").start()

    def _refreshAxisEnabled(self):
        """Read the enabled state on a worker thread and repaint the toggles with it."""
        if not self._axisEnablePainters:
            return

        def read():
            try:
                state = self.driver.is_enabled()
            except Exception:
                self.logger.exception(f"{self.name()}: failed to read axis enabled state")
                return
            if not self._closed:
                self._sigAxisEnabledChanged.emit(tuple(state[ax] for ax in self._axes))

        threading.Thread(target=read, daemon=True, name=f"{self.name()} axis enabled read").start()

    def _paintAxisEnableControls(self, enabled):
        """Draw each toggle for the per-axis *enabled* tuple (GUI thread)."""
        for axes, painter in list(self._axisEnablePainters.items()):
            states = [bool(enabled[i]) for i in axes]
            label = self._axisEnableLabel(axes)
            if all(states):
                color = self.AXIS_ENABLED_COLOR
            elif not any(states):
                color = self.AXIS_DISABLED_COLOR
            else:
                color = self.AXIS_MIXED_COLOR
                label += self.AXIS_MIXED_SUFFIX
            try:
                painter(label, color)
            except UnsupportedControlFeature:
                del self._axisEnablePainters[axes]
                self.logger.warning(f"{self.name()}: {self._axisEnableControls[axes]} cannot show its indicator", exc_info=True)

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


def _nothingCommutated(result) -> bool:
    """True if a ``MagellanPMD.commutate`` result shows every axis was already phased."""
    return all(level is None for level in result.values())


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
    """Stage dock with a homing button."""

    def __init__(self, dev: PMDStage, win):
        StageInterface.__init__(self, dev, win)
        group = Qt.QGroupBox("Homing")
        layout = Qt.QGridLayout()
        group.setLayout(layout)
        self.layout.addWidget(group, self.layout.rowCount(), 0)

        self.homeBtn = FutureButton(
            self.homeClicked, 'Home axes', stoppable=False, raiseOnError=False,
            processing='Homing...',
        )
        self.homeBtn.setToolTip("Find the centre flag on each axis and zero there. Sweeps the full travel.")
        layout.addWidget(self.homeBtn, 0, 0)
        # FutureButton.reset() after a Stopped task leaves a non-stoppable button disabled
        self.homeBtn.sigFinished.connect(lambda task: self.homeBtn.setEnabled(True))

        dev.sigActionFinished.connect(self.actionFinished)

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
