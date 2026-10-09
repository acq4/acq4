from teleprox import RemoteCallException

from acq4.drivers.dovermotion.motionsynergy_client import get_client
from acq4.util import Qt
from acq4.util.task import ManualQtFriendlyTask
from ..ControlSurface import UnsupportedControlFeature
from ..Stage import Stage, MoveFuture


class DoverStage(Stage):
    """
    A DoverMotion stage device.

    Device coordinates are mm, as the MotionSynergy driver works in mm: that is what
    :meth:`~acq4.devices.Stage.Stage.Stage.getPosition`, :meth:`_move` and the ``limits:``
    block carry, and why ``scale`` is 1e-3 per axis. Speeds cross the Stage API in m/s and
    are multiplied by 1e3 for the driver.

    Additional config options::

        dllPath : str
            Path to the MotionSynergy DLLs.
        defaultAcceleration : float
            Acceleration (mm/s^2) used when a move does not specify one. Default
            :attr:`DEFAULT_ACCELERATION_MM_S2`. Passed to the driver unchanged and
            reported in SI by :attr:`acceleration`; the base class's ``acceleration``
            config key is not read here.
        targetUpdateRate : float
            Rate (Hz) the driver aims to report position at, overriding its default of
            20. 20Hz is about all the MotionSynergy API yields while the stage is moving;
            see ``DEFAULT_TARGET_UPDATE_RATE`` in
            ``acq4/drivers/dovermotion/control_thread.py``.
            :attr:`positionUpdatesPerSecond` reports what is actually achieved.
        controls : dict
            Control-surface bindings, as documented on
            :class:`~acq4.devices.Stage.Stage.Stage`. Besides the axis dials the base
            class claims, this device accepts axis-enable toggles: ``enableX``,
            ``enableY`` and ``enableZ``, plus ``enableXY`` covering x and y together.
            Pressing one enables the axes it covers, or disables them if all are already
            enabled. Labels are the axis letters, drawn on :attr:`AXIS_ENABLED_COLOR`
            while enabled and :attr:`AXIS_DISABLED_COLOR` while disabled; a multi-axis
            toggle whose axes disagree (reachable via the MotionSynergy tray menu, or at
            startup) draws :attr:`AXIS_MIXED_COLOR` under a label carrying
            :attr:`AXIS_MIXED_SUFFIX`. A control that cannot draw text shows the colour
            alone; see :meth:`_bindAxisEnableIndicator`.

            Binding ``enableXY`` together with ``enableX`` or ``enableY`` raises
            ``ValueError`` at startup. ``enableZ`` goes with either spelling.

    Example configuration::

        DoverStage:
            driver: 'DoverStage'
            dllPath: 'C:/Program Files/Dover Motion/MotionSynergy'
            controls:
                x: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 0], 'step': 5*um}
                y: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 1], 'step': 5*um}
                z: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 2], 'step': 5*um}
                enableXY: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 0]}
                enableZ: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 1]}

    Example configuration with one toggle per axis::

        DoverStage:
            driver: 'DoverStage'
            dllPath: 'C:/Program Files/Dover Motion/MotionSynergy'
            controls:
                enableX: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 0]}
                enableY: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 1]}
                enableZ: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 2]}
    """

    #: Background colour of an axis-enable toggle while every axis it covers is enabled.
    AXIS_ENABLED_COLOR = (40, 167, 69)

    #: Background colour of an axis-enable toggle while every axis it covers is disabled.
    AXIS_DISABLED_COLOR = (180, 30, 30)

    #: Background colour of a toggle whose axes disagree; only a multi-axis toggle can show it.
    AXIS_MIXED_COLOR = (255, 170, 0)

    #: Appended to a toggle's label while its axes disagree, e.g. ``'XY!'``.
    AXIS_MIXED_SUFFIX = '!'

    #: Internal: hops the driver's enabled-state callback, which arrives on the control
    #: thread, onto the GUI thread before anything repaints a control.
    _sigAxisEnabledChanged = Qt.Signal(object)  # per-axis enabled-state tuple

    #: Acceleration (mm/s²) programmed when the config names none.
    DEFAULT_ACCELERATION_MM_S2 = 50.0

    #: ``MoveContinuous`` retargets in ~1.3ms vs ~230ms through ``Stop()``.
    canRetargetInFlight = True

    @property
    def acceleration(self) -> float:
        """Acceleration (m/s²) the driver is programmed with, converted from mm/s²."""
        return self.config.get("defaultAcceleration", self.DEFAULT_ACCELERATION_MM_S2) * 1e-3

    def __init__(self, man, config: dict, name):
        # Initialized before Stage.__init__: bindControl() runs inside it and reads these.
        self._axisEnableControls = {}  # tuple of axis indices -> Control
        self._axisEnablePainters = {}  # tuple of axis indices -> callable(label, color)
        Stage.__init__(self, man, config, name)
        self._sigAxisEnabledChanged.connect(self._paintAxisEnableControls, Qt.Qt.QueuedConnection)
        self.msapi = get_client(dll_path=config["dllPath"])
        self.dev = self.msapi['smartstage']
        self.dev.default_acceleration = config.get(
            "defaultAcceleration", self.DEFAULT_ACCELERATION_MM_S2
        )
        if "targetUpdateRate" in config:
            self.dev.set_target_update_rate(config["targetUpdateRate"])
        self.dev.enable()
        self._lastMove = None
        self.posChanged(self.dev.pos(refresh=True))
        self.dev.set_callback(self.posChanged)
        if self._axisEnableControls:
            # the control thread polls the enabled state and calls this on every change
            self.dev.set_enabled_callback(self._sigAxisEnabledChanged.emit)
            self._paintAxisEnableControls(self.dev.is_enabled())

    def axes(self):
        return "x", "y", "z"

    # ------------------------------------------------------- axis-enable toggle controls

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
        """Return the axis groups an enable toggle can cover, as tuples of axis indices.

        One group per axis, plus x and y together (when the stage has both).
        """
        axes = list(self.axes())
        groups = [(i,) for i in range(len(axes))]
        if 'x' in axes and 'y' in axes:
            groups.append((axes.index('x'), axes.index('y')))
        return groups

    def _axisEnableName(self, axes) -> str:
        """Return the ``controls:`` name of the enable toggle covering axis indices *axes*."""
        return f'enable{self._axisEnableLabel(axes)}'

    def _axisEnableLabel(self, axes) -> str:
        """Return the label drawn on the enable toggle covering axis indices *axes*.

        The axis letters uppercased and in axis order, e.g. ``'X'``, ``'XY'``.
        """
        names = self.axes()
        return ''.join(str(names[axis]) for axis in axes).upper()

    def _axisEnableDescription(self, axes) -> str:
        """Return ``"axis 'x'"`` or ``"axes 'x' and 'y'"`` for axis indices *axes*."""
        names = [repr(str(self.axes()[axis])) for axis in axes]
        if len(names) == 1:
            return f'axis {names[0]}'
        return 'axes ' + ' and '.join((', '.join(names[:-1]), names[-1]))

    def _bindAxisEnable(self, name, axes, control):
        """Bind *control* as the enable toggle for the axes with indices *axes*.

        Parameters
        ----------
        name : str
            The ``controls:`` key this toggle was declared under.
        axes : tuple of int
            Indices of the axes it covers.
        control : Control
            The control, already acquired for this device.

        Raises
        ------
        ValueError
            If a toggle already bound shares an axis with this one.
        """
        for bound in self._axisEnableControls:
            shared = tuple(axis for axis in axes if axis in bound)
            if shared:
                raise ValueError(
                    f"{self.name()}: control {name!r} covers "
                    f"{self._axisEnableDescription(axes)}, which {self._axisEnableName(bound)!r} "
                    f"already toggles ({self._axisEnableDescription(shared)} in common). Bind one "
                    f"or the other, not both."
                )
        self._axisEnableControls[axes] = control
        control.sigPressed.connect(self._axisEnablePressed)
        self._bindAxisEnableIndicator(axes, control)

    def _bindAxisEnableIndicator(self, axes, control):
        """Record once how *control* draws the state of the axes with indices *axes*.

        Stores a ``painter(label, color)`` in ``_axisEnablePainters``, preferring one
        ``setText`` write (label and background together) over a bare ``setColor``. Each
        candidate is probed by painting the disabled state; one raising
        :class:`UnsupportedControlFeature` is passed over, since having the method does not
        mean this particular control can do it. A control that supports neither is logged
        once here and left out of ``_axisEnablePainters``; it still toggles its axes.

        Parameters
        ----------
        axes : tuple of int
            Indices of the axes this control toggles.
        control : Control
            The control, already acquired for this device.
        """
        label = self._axisEnableLabel(axes)
        described = self._axisEnableDescription(axes)
        candidates = []
        if hasattr(control, 'setText') and control.capabilities()['output'].get('text'):
            candidates.append(('text', lambda text, color: control.setText(text, background=color)))
        if hasattr(control, 'setColor'):
            candidates.append(('color', lambda text, color: control.setColor(color)))
        for kind, painter in candidates:
            try:
                painter(label, self.AXIS_DISABLED_COLOR)
            except UnsupportedControlFeature:
                continue  # the class offers it, this control does not
            self._axisEnablePainters[axes] = painter
            if kind == 'color':
                self.logger.warning(
                    f"{self.name()}: {control} cannot draw text, so it indicates the state"
                    f" of {described} as a bare colour, with no {label!r} label."
                )
            return
        self.logger.warning(
            f"{self.name()}: {control} can show neither the {label!r} label nor the"
            f" axis-enable colours, so it will not indicate the state of {described}."
            f" The toggle still works."
        )

    def _axisEnablePressed(self, control):
        """Toggle the axes whose enable control was pressed.

        Does not repaint: enable/disable are queued, so the repaint waits for the driver's
        enabled-state callback.
        """
        for axes, ctl in self._axisEnableControls.items():
            if ctl is control:
                self._toggleAxisGroup(axes)
                return

    def _paintAxisEnableControls(self, enabled):
        """Draw each axis-enable toggle for the per-axis *enabled* state tuple.

        Runs on the GUI thread. *enabled* may be None, which the driver reports until it
        has read the state; an axis of unknown state is painted as disabled. A toggle
        whose axes disagree gets :attr:`AXIS_MIXED_COLOR` and :attr:`AXIS_MIXED_SUFFIX`.
        A control that raises :class:`UnsupportedControlFeature` here is logged once and
        dropped from ``_axisEnablePainters``.
        """
        for axes, painter in list(self._axisEnablePainters.items()):
            states = self._axisEnabledStates(axes, enabled)
            label = self._axisEnableLabel(axes)
            if all(states):
                color = self.AXIS_ENABLED_COLOR
            elif not any(states):
                color = self.AXIS_DISABLED_COLOR
            else:
                color = self.AXIS_MIXED_COLOR
                label += self.AXIS_MIXED_SUFFIX
            control = self._axisEnableControls[axes]
            try:
                painter(label, color)
            except UnsupportedControlFeature:
                del self._axisEnablePainters[axes]
                self.logger.warning(
                    f"{self.name()}: {control} cannot show its axis-enable indicator, so it"
                    f" will not indicate the state of {self._axisEnableDescription(axes)}",
                    exc_info=True,
                )
            except Exception:
                self.logger.exception(f"{self.name()}: failed to paint {control}")

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

    def stop(self, reason=None):
        """Stop the stage immediately."""
        return self.dev.stop()

    def _getPosition(self):
        return self.dev.pos()

    @property
    def positionUpdatesPerSecond(self):
        """Return the rate (Hz) at which the driver is currently reporting position.

        Measured by the driver's control thread, not computed from its poll interval:
        reading three axes over the MotionSynergy API costs more than the interval, so
        the nominal figure runs ~2.5x high. Costs one RPC round trip per read; cache it
        rather than calling per frame.
        """
        return self.dev.updates_per_second()

    def _move(self, pos, speed, linear, name=None, **kwds):
        """Start a move to *pos* (device coordinates, mm) at *speed* (m/s, or 'fast'/'slow').

        The speed is resolved to m/s here; :class:`DoverMoveFuture` converts it to the
        driver's mm/s. *linear* is ignored: the stage always moves all axes together.
        """
        speed = self._interpretSpeed(speed)
        self._lastMove = DoverMoveFuture(self, pos, speed, name=name)
        return self._lastMove

    def _toggleAxisGroup(self, axes):
        """Drive every axis in *axes* to one enabled state, chosen from a single read.

        Disabled only when all are already enabled, enabled otherwise, so a mismatched
        group resolves to enabled. One decision for the whole group rather than a toggle
        per axis: the requests are queued on the driver's control thread, and a repeated
        press then repeats the same decision instead of swapping axes past each other.
        ``enable_axis``/``disable_axis`` no-op on axes already in the target state.

        Parameters
        ----------
        axes : tuple of int
            Indices of the axes to drive.
        """
        target = not all(self._axisEnabledStates(axes, self.dev.is_enabled()))
        for axis in axes:
            if target:
                self.dev.enable_axis(axis)
            else:
                self.dev.disable_axis(axis)

    @staticmethod
    def _axisEnabledStates(axes, enabled) -> list:
        """Return the enabled flag of each axis in *axes*, from driver state *enabled*.

        *enabled* is the driver's per-axis tuple, None until the control thread has read
        the state; an axis of unknown state counts as disabled.
        """
        return [
            enabled is not None and axis < len(enabled) and bool(enabled[axis]) for axis in axes
        ]

    def quit(self):
        # _teardown() rather than Stage.quit(): that calls stop(), which needs self.dev.
        # The driver's enabled-state callback slot is a single reference, so clear it only
        # if __init__ set it.
        hadEnableControls = bool(self._axisEnableControls)
        Stage._teardown(self)
        self._axisEnableControls = {}
        self._axisEnablePainters = {}
        if hasattr(self, 'dev') and self.dev is not None:
            if hadEnableControls:
                self.dev.set_enabled_callback(None)
            self.dev.set_callback(None)


class DoverMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Dover stage.

    *pos*, :attr:`startPos` and :attr:`targetPos` are device coordinates (mm);
    :attr:`speed` is m/s and is multiplied by 1e3 for the driver's mm/s. Acceleration is
    not set per move; the driver applies ``SmartStage.default_acceleration`` (mm/s^2).
    """

    def __init__(self, dev, pos, speed, name=None):
        MoveFuture.__init__(self, dev, pos, speed, name=name)
        self._future = self.dev.dev.move(list(pos), self.speed * 1e3, name=name)
        self._future.set_callback(self._future_finished)

    @staticmethod
    def _supersededReason(req_fut):
        """Why the driver request was superseded, or None.

        Returns None against a MotionSynergy server too old to report supersession; such
        a server stops the move instead, which arrives as an error. *req_fut* is normally
        a teleprox proxy, which reports a missing attribute as a ``RemoteCallException``
        naming ``AttributeError`` rather than raising one.
        """
        try:
            return req_fut.superseded._get_value()
        except AttributeError:
            return None
        except RemoteCallException as exc:
            if exc.type_str == 'AttributeError':
                return None
            raise

    def _future_finished(self, req_fut):
        # Fires on a driver thread with no context of its own; the throughline reattaches
        # completion to the requesting operation.
        with self.throughlineContext():
            if self.is_stopped:
                return
            superseded = self._supersededReason(req_fut)
            if superseded is not None:
                # Re-aimed in flight rather than halted. Completed with Stopped, not as
                # an arrival: the driver request succeeds at the *new* target, which is
                # not the one this future was asked for.
                if not self.is_done:
                    ManualQtFriendlyTask.stop(self, superseded, wait=False)
                return
            error = req_fut.error._get_value()
            if error is not None:
                excInfo = req_fut.exc_info._get_value()
                if excInfo is not None and excInfo[1] is not None:
                    self.fail(excInfo[1])
                else:
                    self.fail(RuntimeError(str(error)))
            else:
                self.resolve(None)
