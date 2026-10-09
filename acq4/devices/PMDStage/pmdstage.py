from __future__ import annotations

import threading

from acq4.drivers.pmdmotion import MagellanPMD, NotCommutatedError
from acq4.drivers.pmdmotion.protocol import ProfileMode
from acq4.drivers.stage import MoveStopped
from acq4.util import Qt
from acq4.util.task import FutureButton, ManualQtFriendlyTask
from ..Stage import MoveFuture, Stage, StageInterface

#: Encoder counts per mm on a Dover SmartStage (5 nm/count).
DEFAULT_COUNTS_PER_MM = 200_000

#: Worst-case travel (mm) of one axis during algorithmic commutation.
COMMUTATION_TRAVEL_MM = 20.64

#: Distance (mm) Z drops when its motor output is removed.
Z_SAG_MM = 15

#: Default position change (mm) that triggers a position update; above encoder noise (~50 nm).
DEFAULT_POSITION_CHANGE_THRESHOLD_MM = 2.5e-4


class PMDStage(Stage):
    """A Dover SmartStage driven directly over the PMD Magellan serial protocol.

    Device coordinates are mm (the driver is built with ``counts_per_unit`` counts per
    mm), so ``scale`` defaults to 1e-3 per axis. Speeds cross the Stage API in m/s and
    are multiplied by 1e3 for the driver.

    If any axis is not commutated at startup (after a power cycle) the device still
    loads: those axes refuse to move until :meth:`commutate` succeeds. Commutation and
    :meth:`home` move the stage a long way and cannot be interrupted; the device dock
    asks for confirmation before running either.

    Config options::

        motionSynergyPath : str
            MotionSynergy folder whose ``SupportFolder/Instrument.cfg`` names the serial
            port; used for port discovery when ``port`` is None.
        port : str | None
            Serial port override. Default None (discover).
        baudrate : int
            Default 57600.
        axes : dict
            Axis name -> RS-485 node ID. Default ``{'x': 1, 'y': 2, 'z': 3}``.
        counts_per_unit : float
            Encoder counts per mm. Default 200000.
        poll_interval : float
            Seconds between position polls. Default 0.025.
        positionChangeThreshold : float
            Movement (mm) on any axis needed to report a new position while idle or
            moving. Default 2.5e-4 (250 nm). The position is always reported when a
            move ends.
        acceleration : float
            Acceleration (m/s²) programmed for every move. Default: the driver's
            (400 mm/s²).
        jerk : float
            Jerk (m/s³) for S-curve moves. Default: the driver's (50000 mm/s³).
        profile : str
            'trapezoidal' (default) or 'scurve'.

    Example configuration::

        Stage:
            driver: 'PMDStage'
            motionSynergyPath: 'C:/Program Files/Dover Motion/MotionSynergy'
            axes: {'x': 1, 'y': 2, 'z': 3}
            counts_per_unit: 200000
            scale: 1e-3, 1e-3, 1e-3
    """

    #: Emitted with the list of unphased axes whenever it may have changed.
    sigPhasingChanged = Qt.Signal(object)

    #: Emitted with ``(action, exception or None)`` when a commutate/home finishes.
    sigActionFinished = Qt.Signal(object, object)

    driverClass = MagellanPMD

    def __init__(self, man, config: dict, name):
        self._axes = tuple(config.get('axes', {'x': 1, 'y': 2, 'z': 3}))
        config.setdefault('scale', (1e-3,) * len(self._axes))
        self._actionLock = threading.Lock()
        self._activeAction = None  # (name, task) of a running commutate/home

        self.driver = self._makeDriver(config)
        notCommutated = None
        try:
            self.driver.connect()
        except NotCommutatedError as exc:
            notCommutated = exc  # still connected and polling
        try:
            # trapezoidal moves retarget in flight; S-curve moves stop first
            self.canRetargetInFlight = self.driver.default_profile == ProfileMode.TRAPEZOIDAL
            Stage.__init__(self, man, config, name)
            self._lastPos = None
            self.posChanged(self._posFromDriver(self.driver.get_position() or {}))
            self.driver.set_position_callback(self._driverPositionChanged)
        except Exception:
            self.driver.close()
            raise

        if notCommutated is not None:
            self.logger.warning(
                f"{self.name()}: axes {', '.join(notCommutated.axes)} are not commutated (stage was "
                f"power-cycled) and cannot move. Use 'Commutate' in the {self.name()} dock, then "
                f"'Home axes'. Commutation moves each axis up to {COMMUTATION_TRAVEL_MM} mm."
            )

    def _makeDriver(self, config):
        kwds = {}
        if config.get('acceleration') is not None:
            kwds['acceleration'] = config['acceleration'] * 1e3
        if config.get('jerk') is not None:
            kwds['jerk'] = config['jerk'] * 1e3
        if config.get('profile') is not None:
            kwds['profile'] = config['profile']
        return self.driverClass(
            dict(config.get('axes', {'x': 1, 'y': 2, 'z': 3})),
            port=config.get('port'),
            motion_synergy_path=config.get('motionSynergyPath'),
            baudrate=config.get('baudrate', 57600),
            counts_per_unit=config.get('counts_per_unit', DEFAULT_COUNTS_PER_MM),
            poll_interval=config.get('poll_interval', 0.025),
            position_change_threshold=config.get(
                'positionChangeThreshold', DEFAULT_POSITION_CHANGE_THRESHOLD_MM),
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
        last = self._lastPos or [0.0] * len(self._axes)
        return [float(pos[ax]) if ax in pos else last[i] for i, ax in enumerate(self._axes)]

    def _driverPositionChanged(self, pos):
        # driver control thread
        self.posChanged(self._posFromDriver(pos))

    def _getPosition(self):
        return self._posFromDriver(self.driver.get_position() or {})

    # ---- motion ----

    def unphasedAxes(self) -> list:
        """Axes that need commutation before they can move."""
        return self.driver.unphased_axes()

    def _move(self, pos, speed, linear, name=None, **kwds):
        """Start a move to *pos* (mm; None = stay) at *speed* (m/s or 'fast'/'slow').

        *linear* is ignored: multi-axis moves are always straight lines. An unphased
        axis whose target is its current position is left out; one that would move
        raises NotCommutatedError.
        """
        action = self._activeAction
        if action is not None:
            raise RuntimeError(f"{self.name()}: cannot move while {action[0]} is running")
        pos = list(pos)
        unphased = set(self.unphasedAxes())
        if unphased:
            current = self.getPosition()
            blocked = []
            for i, ax in enumerate(self._axes):
                if ax in unphased and pos[i] is not None:
                    if abs(pos[i] - current[i]) <= 1e-3:
                        pos[i] = None
                    else:
                        blocked.append(ax)
            if blocked:
                raise NotCommutatedError(
                    blocked,
                    f"{self.name()}: axes {', '.join(blocked)} are not commutated; run Commutate "
                    f"from the device dock first",
                )
        speed = self._interpretSpeed(speed)
        self._lastMove = PMDMoveFuture(self, pos, speed, name=name, **kwds)
        return self._lastMove

    def stop(self, reason=None):
        """Stop all axes; the active move completes as stopped."""
        return self.driver.stop(reason or 'stop requested')

    # ---- commutation and homing ----

    def commutate(self, axes=None) -> ManualQtFriendlyTask:
        """Commutate *axes* (default all); returns a task completing when done.

        MOVES each axis up to 20.64 mm in an unpredictable direction, and cannot be
        interrupted; Z first drops ~15 mm when its motor output is removed.
        """
        return self._runAction('commutation', self.driver.commutate, axes)

    def home(self, axes=None) -> ManualQtFriendlyTask:
        """Home *axes* (default all) on the centre vane, zeroing their position.

        Sweeps up to the full travel and cannot be interrupted. Axes must be commutated.
        """
        return self._runAction('homing', self.driver.home, axes)

    def actionWarning(self, action: str, axes) -> str:
        """Confirmation text for 'commutation' or 'homing' of *axes*."""
        axes = list(axes)
        names = ', '.join(ax.upper() for ax in axes)
        if action == 'commutation':
            text = (
                f"Commutate {self.name()} axes {names}?\n\n"
                f"Commutation moves each axis up to {COMMUTATION_TRAVEL_MM} mm, in a direction that "
                f"cannot be predicted, and CANNOT BE INTERRUPTED once started. Make sure every axis "
                f"has at least {COMMUTATION_TRAVEL_MM} mm of clearance in both directions."
            )
            if 'z' in axes:
                text += (
                    f"\n\nZ WARNING: Z drops about {Z_SAG_MM} mm the moment its motor output is "
                    f"removed, before commutation even begins. Raise or remove pipettes and make sure "
                    f"nothing (objective, chamber, pipettes) is below the stage."
                )
        else:
            text = (
                f"Home {self.name()} axes {names}?\n\n"
                f"Homing sweeps each axis up to its full travel to find the centre flag and resets "
                f"its zero position. It CANNOT BE INTERRUPTED once started. Make sure the full "
                f"range of motion is clear."
            )
            if 'z' in axes:
                text += (
                    "\n\nZ WARNING: Z may travel its full stroke downward. Raise or remove pipettes "
                    "and make sure nothing (objective, chamber, pipettes) is below the stage."
                )
        return text

    def _runAction(self, action, driverCall, axes) -> ManualQtFriendlyTask:
        """Run a driver commutate/home call; the task resolves or fails with the request."""
        axes = None if axes is None else list(axes)
        task = ManualQtFriendlyTask(name=f"{self.name()} {action}")
        with self._actionLock:
            if self._activeAction is not None:
                raise RuntimeError(f"{self.name()}: {self._activeAction[0]} is already running")
            self._activeAction = (action, task)
        try:
            self.logger.info(f"{self.name()}: starting {action} of axes {axes or 'all'}")
            request = driverCall(axes=axes)
        except Exception:
            self._activeAction = None
            raise

        def waitForRequest():
            exc = None
            try:
                result = request.wait(timeout=None)
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
        except Exception:
            pass
        # the threshold may have suppressed the final position
        dev = self.dev
        dev.posChanged(dev._getPosition())
        try:
            self.request.wait(timeout=0)
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
            f"Phase-initialize the motors. Moves each axis up to {COMMUTATION_TRAVEL_MM} mm; "
            f"cannot be interrupted."
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
        axes = self.dev.unphasedAxes() or list(self.dev.axes())
        if not self.confirm("Commutate stage", self.dev.actionWarning('commutation', axes)):
            return self._declined('commutation')
        return self.dev.commutate(axes)

    def homeClicked(self):
        unphased = self.dev.unphasedAxes()
        if unphased:
            self.showMessage(
                "Commutate first",
                f"Axes {', '.join(ax.upper() for ax in unphased)} must be commutated before homing.",
            )
            return self._declined('homing')
        axes = list(self.dev.axes())
        if not self.confirm("Home stage", self.dev.actionWarning('homing', axes)):
            return self._declined('homing')
        return self.dev.home(axes)

    def actionFinished(self, action, exc):
        if exc is not None:
            self.showMessage(f"{self.dev.name()} {action} failed", f"{action.capitalize()} failed:\n\n{exc}")

    def showMessage(self, title, text):
        """Show an error/notice box; tests override this."""
        Qt.QMessageBox.critical(self, title, text)
