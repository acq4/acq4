from acq4.drivers.dovermotion.motionsynergy_client import get_client
from acq4.util import Qt
from ..ControlSurface import UnsupportedControlFeature
from ..Stage import Stage, MoveFuture


class DoverStage(Stage):
    """
    A DoverMotion stage device.

    Additional config options::

        dllPath : str
            Path to the MotionSynergy DLLs.
        defaultAcceleration : float
            Acceleration (mm/s^2) used when a move does not specify one. Default
            :attr:`DEFAULT_ACCELERATION_MM_S2`. Passed to the driver unchanged, and
            reported in SI by :attr:`acceleration`; the base class's ``acceleration``
            config key is not read here, since this is the figure the hardware is
            actually given.
        targetUpdateRate : float
            Rate (Hz) the driver aims to report position at, overriding its default of
            20. Leave it alone unless you have measured this rig: 20Hz is about all the
            MotionSynergy API gives up while the stage is moving, and asking for more
            only means the loop never waits. See ``DEFAULT_TARGET_UPDATE_RATE`` in
            ``acq4/drivers/dovermotion/control_thread.py`` for the measurements.
            :attr:`positionUpdatesPerSecond` reports what is actually achieved.
        controls : dict
            Control-surface bindings, as documented on
            :class:`~acq4.devices.Stage.Stage.Stage`. In addition to the axis dials the
            base class claims, this device accepts axis-enable toggles: one per axis,
            named ``enableX``, ``enableY`` and ``enableZ``, and one covering x and y
            together, named ``enableXY``. Pressing a toggle enables or disables the axes
            it covers, and the control shows their letters on a background of
            :attr:`AXIS_ENABLED_COLOR` while they are enabled and
            :attr:`AXIS_DISABLED_COLOR` while they are disabled. Labels come from the axis
            names and need no configuration; see :meth:`_bindAxisEnableIndicator` for what
            a control that cannot draw text shows instead.

            ``enableXY`` drives both axes with one decision, so no press of it can leave x
            enabled and y disabled. They can still disagree without it -- the stage comes
            up however it was left, and the MotionSynergy tray menu enables and disables
            each axis on its own -- so a mismatch is drawn as a third field,
            :attr:`AXIS_MIXED_COLOR` under a label carrying :attr:`AXIS_MIXED_SUFFIX`
            (``'XY!'``), rather than as a confident green or red about half the stage. A
            press from there enables both, as does a press with both disabled; only a
            press with both already enabled disables them. Enabling is the direction that
            resolves a mismatch without taking holding current off an axis somebody had
            enabled, and is the state :meth:`__init__` puts every axis in anyway.

            Binding ``enableXY`` *and* ``enableX`` (or ``enableY``) raises ``ValueError``
            at startup. Two keys with authority over one axis cannot both be right: press
            one and the other's indicator is stale, with nothing on the panel to say which
            key last won. Bind one spelling or the other. ``enableZ`` is independent of
            all of this and goes with either.

    Units: the MotionSynergy driver works in mm, so this device's coordinates are mm --
    that is what :meth:`~acq4.devices.Stage.Stage.Stage.getPosition`, :meth:`_move` and
    the ``limits:`` block carry, and why ``scale`` is 1e-3 per axis. Speeds crossing the
    Stage API are in m/s and are multiplied by 1e3 here to reach the driver's mm/s.

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

    Example configuration with one toggle per axis, which is the same device with
    ``enableXY`` unbound::

        DoverStage:
            driver: 'DoverStage'
            dllPath: 'C:/Program Files/Dover Motion/MotionSynergy'
            controls:
                enableX: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 0]}
                enableY: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 1]}
                enableZ: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 2]}
    """

    #: Background colour of an axis-enable toggle while every axis it covers is enabled.
    #: These toggles live on the Stream Dock, whose keys are small RGB displays, so the key
    #: is the axis letters on a green field. All three of these colours have green in them,
    #: so an X-Keys key (one blue and one red LED) refuses every one of them, which is why
    #: such a key indicates nothing at all rather than losing only the mixed state; see
    #: :meth:`_bindAxisEnableIndicator`.
    AXIS_ENABLED_COLOR = (40, 167, 69)

    #: Background colour of an axis-enable toggle while every axis it covers is disabled.
    AXIS_DISABLED_COLOR = (180, 30, 30)

    #: Background colour of a toggle whose axes disagree -- some enabled, some not. Amber:
    #: a third field, so that a mismatch reads as neither settled state. Only a toggle
    #: covering more than one axis can show it; a single axis cannot disagree with itself.
    AXIS_MIXED_COLOR = (255, 170, 0)

    #: Appended to a toggle's label while its axes disagree, e.g. ``'XY!'``. Red, green and
    #: amber are three fields that red-green colour blindness cannot be relied on to
    #: separate, so the mismatch is in the glyphs too wherever the control can draw them.
    AXIS_MIXED_SUFFIX = '!'

    #: Internal: hops the driver's enabled-state callback, which arrives on the control
    #: thread, onto the GUI thread before anything repaints a control.
    _sigAxisEnabledChanged = Qt.Signal(object)  # per-axis enabled-state tuple

    #: Acceleration (mm/s^2) programmed when the config names none. The driver's own
    #: default is lower; this is the figure the rigs in service run at.
    DEFAULT_ACCELERATION_MM_S2 = 50.0

    @property
    def acceleration(self) -> float:
        """Acceleration (m/s^2) the driver is programmed with, converted from mm/s^2.

        ``defaultAcceleration`` is in the driver's units (mm/s^2), so the config's 50
        is 0.05 m/s^2 -- a factor of a thousand, and the one that matters: getting it
        backwards would predict move durations 30x out either way. Read from the config
        rather than from ``self.dev.default_acceleration`` because the latter is an
        attribute on a MotionSynergy proxy and every read is an RPC round trip; the two
        are set from the same expression in :meth:`__init__`.
        """
        return self.config.get("defaultAcceleration", self.DEFAULT_ACCELERATION_MM_S2) * 1e-3

    def __init__(self, man, config: dict, name):
        # bindControl() runs inside Stage.__init__, before self.dev exists, so these must
        # be ready first and the binding must not touch the stage hardware. It does write
        # to the control surface, which is a different device and already constructed.
        self._axisEnableControls = {}  # tuple of axis indices -> Control
        # how each toggle shows its state, settled once by _bindAxisEnableIndicator();
        # a toggle that can indicate nothing has no entry here
        self._axisEnablePainters = {}  # tuple of axis indices -> callable(label, color)
        Stage.__init__(self, man, config, name)
        self._sigAxisEnabledChanged.connect(self._paintAxisEnableControls, Qt.Qt.QueuedConnection)
        self.msapi = get_client(dll_path=config["dllPath"])
        self.dev = self.msapi['smartstage']
        self.dev.default_acceleration = config.get(
            "defaultAcceleration", self.DEFAULT_ACCELERATION_MM_S2
        )
        # set rather than passed to the constructor: the MotionSynergy server outlives
        # the ACQ4 sessions that connect to it, so the control thread we are configuring
        # here has usually been running since before this session started.
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

        One group per axis, plus x and y together. Those two move the specimen in the
        plane and are the pair a rig owner enables and disables as a unit -- one key for
        both of them, which is also one fewer key to mismatch. z keeps its own toggle: it
        carries the objective, and is the axis worth disabling by itself.

        A stage whose axes are not called x and y gets the per-axis groups only.
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

        The axis letters, uppercased and in axis order -- ``'X'``, ``'XY'`` -- derived
        from the axis names so that no rig configuration is needed, and matching the
        ``enableX`` and ``enableXY`` names the toggles are bound by. Two glyphs is also
        about as much as a 72x72 key shows legibly, and which state the axes are in is the
        background colour rather than more words -- except for the mismatch
        :attr:`AXIS_MIXED_SUFFIX` marks, which is worth a glyph of its own.
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
            If a toggle already bound covers one of these axes -- ``enableXY`` together
            with ``enableX``, say. Two keys with authority over one axis cannot both be
            right: press either and the other's indicator is stale, with nothing on the
            panel to say which key last won, and the rig owner reads a confident colour
            off a key that is no longer in charge. There is no useful reading of that, so
            it is refused here, at startup, rather than shipped to the bench.
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
        """Work out once how *control* shows the state of the axes with indices *axes*.

        Output belongs to each control surface rather than to a generic interface, so
        this asks the control what it offers, keeping as much of the indicator as each
        one can carry:

        * a control that draws text takes the whole indicator -- the axis letters on a
          state-coloured background, in one ``setText`` write, so that the label and the
          colour can never disagree on the panel;
        * a control that only takes a colour keeps the colour and loses the label, which
          is what this device drew before the labels existed. A multi-axis toggle there
          still shows its mismatch, as :attr:`AXIS_MIXED_COLOR`, but without the
          :attr:`AXIS_MIXED_SUFFIX` glyph to back the colour up;
        * a control that can show neither indicates nothing, and is said so here rather
          than on every state change.

        Having the method is not proof the control has the output -- one control class
        covers a surface's keys *and* its dials, and none of these colours is reachable on
        a key lit by one blue and one red LED, the mixed amber included -- so each
        candidate is tried once, on the disabled state the axes are in before
        :meth:`__init__` enables them, and one that refuses is passed over. That one probe
        stands in for all three states: a key that cannot show the disabled red will not
        manage the enabled green or the mixed amber either, and a colour refused later is
        dropped by :meth:`_paintAxisEnableControls` instead. Resolving it here means
        :meth:`_paintAxisEnableControls` is a call rather than a decision; a toggle that
        indicates nothing still enables and disables its axes.

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

        The repaint is left to the driver's enabled-state callback: enabling and
        disabling are queued requests, so the state read back here would still be the
        old one.
        """
        for axes, ctl in self._axisEnableControls.items():
            if ctl is control:
                self._toggleAxisGroup(axes)
                return

    def _paintAxisEnableControls(self, enabled):
        """Draw each axis-enable toggle for the per-axis *enabled* state tuple.

        What each toggle draws -- a labelled, state-coloured key or a bare colour -- was
        settled by :meth:`_bindAxisEnableIndicator`, and a toggle that can indicate
        nothing is not in ``_axisEnablePainters`` at all.

        A toggle covering more than one axis has a third appearance, for the state where
        the axes it covers disagree: :attr:`AXIS_MIXED_COLOR` under a label carrying
        :attr:`AXIS_MIXED_SUFFIX`. Nothing this device does produces that state -- a press
        drives every axis in the group to one target (see :meth:`_toggleAxisGroup`) -- but
        it is reachable all the same, because the stage comes up however it was left and
        the MotionSynergy tray menu enables and disables each axis on its own. Drawn as
        either settled colour it would be a confident lie about half the stage, so it gets
        a field of its own that reads as neither.

        *enabled* may be None, which the driver reports until it has read the state;
        an axis of unknown state is painted as disabled. Runs on the GUI thread.

        A control that turns out to refuse its indicator anyway is reported once and then
        dropped, rather than raising on every state change. It is a configuration mistake
        rather than something to paper over: the alternative is a key that silently
        indicates nothing.
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

        Measured by the driver's control thread as it runs, not computed from its poll
        interval: reading all three axes over the MotionSynergy API costs more than the
        interval itself, so the nominal figure came out around 2.5x the truth, and
        callers that size a sweep by it -- ``acquire_z_stack`` -- swept that much too
        fast for the reports to keep up.

        One RPC round trip to the MotionSynergy server per read, so read it once and
        keep the value rather than calling it per frame.
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

        Disabled only when all of them are already enabled; enabled otherwise. So a group
        whose axes disagree comes out enabled rather than carrying the mismatch forward,
        and the press is one decision applied to the whole group rather than a toggle per
        axis -- which is what keeps x and y from swapping places instead of meeting.
        Enabling is also the direction that resolves a mismatch without taking holding
        current off an axis somebody had enabled, and is the state :meth:`__init__` puts
        every axis in anyway.

        The driver's ``enable_axis``/``disable_axis`` check the axis' state before acting,
        so the axes already in the target state are not disturbed: recovering from a
        mismatch touches only the odd one out. Requests are queued on the control thread,
        so a second press arriving before the first is served reads the same state and
        asks for the same thing again; repeating one decision is harmless, where toggling
        each axis independently would not be.

        Parameters
        ----------
        axes : tuple of int
            Indices of the axes to drive. A one-axis group is the plain toggle.
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

        *enabled* is the driver's per-axis tuple, which is None until the control thread
        has read the state; an axis of unknown state counts as disabled, which is both
        what the toggle paints and what a press works from.
        """
        return [
            enabled is not None and axis < len(enabled) and bool(enabled[axis]) for axis in axes
        ]

    def quit(self):
        # _teardown() rather than Stage.quit(): that calls stop(), which needs self.dev.
        # Unsubscribe from the enabled-state callback only if we subscribed, mirroring
        # __init__; the driver's callback slot is a single reference, so clearing one we
        # never set would steal somebody else's.
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
    :attr:`speed` is m/s, as everywhere in the Stage API, and is multiplied by 1e3 for
    the driver, which wants mm/s. The move's acceleration is not set per move; the
    driver applies ``SmartStage.default_acceleration`` (mm/s^2).
    """

    def __init__(self, dev, pos, speed, name=None):
        MoveFuture.__init__(self, dev, pos, speed, name=name)
        self._future = self.dev.dev.move(list(pos), self.speed * 1e3, name=name)
        self._future.set_callback(self._future_finished)

    def _future_finished(self, req_fut):
        # External producer: the driver request's completion callback completes
        # this promise. Honor a stop already requested on this future. The callback
        # fires on a driver thread with no context of its own, so run under this
        # move's throughline to keep completion attached to the requesting operation.
        with self.throughlineContext():
            if self.is_stopped:
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
