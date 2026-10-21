from __future__ import annotations

from collections import OrderedDict
from threading import RLock

import numpy as np

from acq4.devices.PatchClamp.patchclamp import PatchClamp
from acq4.util import Qt
from acq4.util import ptime
from acq4.util.task import raise_errors
from coorx import Point
from neuroanalysis.test_pulse import PatchClampTestPulse
from .devgui import PatchPipetteDeviceGui
from .statemanager import PatchPipetteStateManager
from ..Camera import Camera
from ..ControlSurface import UnsupportedControlFeature, acquireControlFromConfig
from ..Device import Device
from ..Pipette import Pipette
from ..Pipette.pipette import controlLabelFromConfig
from ..PressureControl import PressureControl
from ..Sonicator import Sonicator

# Event types stored in the in-memory event log and shown in the UI.
LOG_EVENT_TYPES = frozenset({
    'state_event',
    'state_change',
    'new_pipette',
    'pipette_calibrated',
    'move_requested',
    'new_patch_attempt',
    'tip_clean_changed',
})


class PatchPipette(Device):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.

    If you intend this for use with the MultiPatch module, the device name in the configuration
    needs to end in a number.

    Configuration options:

    * **controls** (dict, optional): Physical controls on a
      :class:`~acq4.devices.ControlSurface.ControlSurface` (a Stream Dock, an X-Keys pad) to bind to
      states of this pipette's state machine. The block is a dict of named actions; each value is a
      control address (``device``, ``type``, ``page``, ``key``) plus that action's own options.
      Pressing the control requests that state through :meth:`setState`, so it is exactly the state
      machine's own transition -- profile config, fallbacks, Panic Lock guard and all -- and not a
      shortcut past it.

      The accepted names are the state names :meth:`listStates` reports, which is the registry in
      :attr:`~acq4.devices.PatchPipette.statemanager.PatchPipetteStateManager.stateHandlers`:
      ``out``, ``bath``, ``approach``, ``cell detect``, ``seal``, ``contact cell``,
      ``cell attached``, ``break in``, ``whole cell``, ``clear access``, ``reseal``, ``outside out``,
      ``blowout``, ``broken``, ``fouled``, ``clean``, ``collect``, ``home with nucleus`` and
      ``refill``. Several contain spaces; ``pyqtgraph.configfile`` takes a config key literally, so
      write them bare (``break in:``) and never quoted.

      Per-state options:

      label : str
          Text drawn on the key, where the key can draw text. Defaults to the state name,
          which is what the key said before this option existed. Several state names are
          multi-word and shrink hard on a 72x72 key, so a short label such as ``'cell det'``
          goes here. Spelled as :class:`~acq4.devices.Microscope.Microscope` spells it. An
          explicitly empty label is refused rather than drawn: an unlabelled key is what
          the option exists to avoid.
      setActive : bool
          Passed to :meth:`setState`. Defaults to True.

      Where the control can show something, the key carries its label and is highlighted while
      its state is the active one, driven by :attr:`sigStateChanged`. The highlight is a
      background behind the same text, so a custom label survives every repaint.

      The control surface must be declared *before* this device in ``devices.cfg``: devices are
      constructed in file order and the surface is looked up by name while this device is being
      built, exactly as ``pipetteDevice`` is.

    Example configuration::

        PatchPipette1:
            driver: 'PatchPipette'
            pipetteDevice: 'Pipette1'
            clampDevice: 'Clamp1'
            pressureDevice: 'Pressure1'
            controls:
                out: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [0, 0]}
                bath: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [0, 1]}
                cell detect: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [0, 2], 'label': 'cell det'}
                seal: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [0, 3]}
                break in: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [1, 0]}
                whole cell: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [1, 1]}
                clean: {'device': 'Dock', 'type': 'button', 'page': 1, 'key': [1, 2]}
    """

    sigStateChanged = Qt.Signal(object, object, object)  # self, newState, oldState
    sigActiveChanged = Qt.Signal(object, object)  # self, active
    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure
    sigMoveStarted = Qt.Signal(object)  # self
    sigMoveFinished = Qt.Signal(object, object)  # self, position
    sigTargetChanged = Qt.Signal(object, object)  # self, target
    sigNewPipetteRequested = Qt.Signal(object)  # self
    sigTipCleanChanged = Qt.Signal(object, object)  # self, clean
    sigTipBrokenChanged = Qt.Signal(object, object)  # self, broken
    sigAccessWarningChanged = Qt.Signal(object, object, object)  # self, active, message

    # catch-all signal for event logging
    sigNewEvent = Qt.Signal(object, object)  # self, event

    # emitted every time we finish a patch attempt
    sigPatchAttemptFinished = Qt.Signal(object, object)  # self, patch record

    # These attributes can be modified to customize state management and test pulse acquisition
    defaultStateManagerClass = PatchPipetteStateManager

    def __init__(self, deviceManager, config, name):
        pipName = config.pop('pipetteDevice', None)
        self.pipetteDevice: Pipette = deviceManager.getDevice(pipName)

        clampName = config.pop('clampDevice', None)
        self.clampDevice: PatchClamp | None = None
        if clampName is not None:
            self.clampDevice = deviceManager.getDevice(clampName)
            self.clampDevice.sigStateChanged.connect(self.clampStateChanged)
            self.clampDevice.sigAutoBiasChanged.connect(self._autoBiasChanged)
            self.clampDevice.sigTestPulseFinished.connect(self._testPulseFinished)

        Device.__init__(self, deviceManager, config, name)

        # current state variables
        self.active = False
        self.broken = False
        self.clean = True
        self.calibrated = False
        self.waitingForSwap = False
        self._accessWarning = (False, "")
        self._lastPos = None
        # Tokens held by whoever currently wants test_pulse events to carry the
        # full PatchClampTestPulse object, not just its analysis. A set rather
        # than a bool because independent recorders subscribe independently:
        # with a bool, whichever one stopped last would silence the others.
        # Holds tokens, never the subscribers themselves, so nothing here keeps
        # a recorder alive.
        self._fullTestPulseSubscribers = set()
        self.cell = None
        self.previousCells = []

        # key measurements made during patch process and lifetime of pipette
        self._patchRecord = None
        self._pipetteRecord = None

        # in-memory log of semantically meaningful events; cleared on newPatchAttempt()
        self._logEvents = []
        self._logLock = RLock()

        self.pressureDevice: PressureControl | None = None
        if 'pressureDevice' in config:
            self.pressureDevice = deviceManager.getDevice(config['pressureDevice'])
            if not self.pressureDevice.isValidForPatchPipettes():
                raise ValueError(
                    f"Pressure device {self.pressureDevice.name()} is not valid for use with patch pipettes"
                )
            self.pressureDevice.sigPressureChanged.connect(self.pressureChanged)
        self.userPressure = False

        self.sonicatorDevice: Sonicator | None = None
        if 'sonicatorDevice' in config:
            self.sonicatorDevice = deviceManager.getDevice(config['sonicatorDevice'])
            self.sonicatorDevice.sigSonicationChanged.connect(self.sonicationChanged)

        self._initStateManager()

        self.pipetteDevice.sigCalibrationChanged.connect(self._pipetteCalibrationChanged)
        self.pipetteDevice.sigMoveStarted.connect(self._pipetteMoveStarted)
        self.pipetteDevice.sigMoveFinished.connect(self._pipetteMoveFinished)
        self.pipetteDevice.sigMoveRequested.connect(self._pipetteMoveRequested)
        self.pipetteDevice.sigTargetChanged.connect(self._pipetteTargetChanged)
        self.pipetteDevice.parentDevice().sigPositionChanged.connect(
            self._manipulatorTransformChanged
        )
        self.pipetteDevice.parentDevice().sigOrientationChanged.connect(
            self._manipulatorTransformChanged
        )

        deviceManager.declareInterface(name, ['patchpipette'], self)

        # After _initStateManager(), so that a bound key can be painted with the state the
        # device actually starts in rather than with nothing.
        self._boundControls = {}  # config name -> Control
        self._stateControls = {}  # Control -> binding dict
        self._setupControls(config)

        # restore last known state for this pipette
        lastState = self.readConfigFile('last_state')
        # restoring previous state is temporarily disabled -- this needs a lot more work to be safe.
        # self.setState(lastState.get('state', 'out'))
        # self.broken = lastState.get('broken', False)
        # self.calibrated = lastState.get('calibrated', False)
        # self.setActive(False)  # Always start pipettes disabled rather than restoring last state?
        # # self.setActive(lastState.get('active', False))

    def isTipClean(self):
        return self.clean

    def setTipClean(self, clean):
        if clean == self.clean:
            return
        self.clean = clean
        self.sigTipCleanChanged.emit(self, clean)
        self.emitNewEvent('tip_clean_changed', {'clean': clean})

    def accessWarning(self):
        """Return the current (active, message) access-resistance warning tuple."""
        return self._accessWarning

    def setAccessWarning(self, active, message=""):
        """Raise or clear a whole-cell access-resistance warning for the UI to display.

        Unlike a state change, this is a passive alert: whole cell stays put and the user decides
        whether to initiate a 'clear access' attempt. Emitting with the same active flag is a no-op.
        """
        active = bool(active)
        if self._accessWarning[0] == active:
            return
        self._accessWarning = (active, message)
        self.sigAccessWarningChanged.emit(self, active, message)
        self.emitNewEvent('access_warning_changed', {'active': active, 'info': message})

    def isTipBroken(self):
        return self.broken

    def setTipBroken(self, broken):
        if broken == self.broken:
            return
        self.broken = broken
        self.sigTipBrokenChanged.emit(self, broken)
        self.emitNewEvent('tip_broken_changed', {'broken': broken})
        # states should take care of this, but we want to make sure pressure stops quickly.
        if broken and self.pressureDevice is not None:
            self.pressureDevice.setPressure(pressure=0)

    def scopeDevice(self):
        return self.pipetteDevice.scopeDevice()

    def imagingDevice(self) -> Camera:
        return self.pipetteDevice.imagingDevice()

    def focusOnTip(self, speed, raiseErrors=False):
        imdev = self.imagingDevice()
        fut = imdev.moveCenterToGlobal(
            self.pipetteDevice.globalPosition(), speed=speed, name=f"Focus on {self.name()} tip"
        )
        if raiseErrors:
            raise_errors(fut, "Error while focusing on pipette tip: {error}")
        return fut

    def focusOnTarget(self, speed, raiseErrors=False):
        imdev = self.imagingDevice()
        fut = imdev.moveCenterToGlobal(
            self.pipetteDevice.targetPosition(), speed=speed, name=f"Focus on {self.name()} target"
        )
        if raiseErrors:
            raise_errors(fut, "Error while focusing on pipette target: {error}")
        return fut

    def newPipette(self):
        """A new physical pipette has been attached; reset any per-pipette state."""
        self.setTipBroken(False)
        self.setTipClean(True)
        self.calibrated = False
        self.waitingForSwap = False
        self._pipetteRecord = None
        self.pipetteDevice.setOffset(self.pipetteDevice.averageHistoricOffset())
        self.emitNewEvent('new_pipette', {})
        self.newPatchAttempt()
        self.setState('bath')
        return self.pipetteDevice.findNewPipette()

    def requestNewPipette(self):
        """Call to emit a signal requesting a new pipette."""
        self.waitingForSwap = True
        self.sigNewPipetteRequested.emit(self)

    def pipetteRecord(self):
        if self._pipetteRecord is None:
            self._pipetteRecord = {
                'originalResistance': None,
                'cleanCount': 0,
            }
        return self._pipetteRecord

    def newPatchAttempt(self):
        """Ready to begin a new patch attempt; reset TP history, patch record, and event log."""
        self.finishPatchRecord()
        if self.clampDevice:
            self.clampDevice.resetTestPulseHistory()
        with self._logLock:
            self._logEvents.clear()
        self.emitNewEvent('new_patch_attempt', {})

    def _resetPatchRecord(self):
        self.finishPatchRecord()
        piprec = self.pipetteRecord()
        self._patchRecord = OrderedDict(
            [
                ('patchPipette', self.name()),
                ('pipetteOriginalResistance', piprec['originalResistance']),
                ('pipetteCleanCount', piprec['cleanCount']),
                ('initialResistance', None),
                ('initialOffset', None),
                ('attemptedCellDetect', False),
                ('detectedCell', None),
                ('cellDetectInitialTarget', None),
                ('cellDetectFinalTarget', None),
                ('attemptedSeal', False),
                ('sealSuccessful', None),
                ('fouledBeforeSeal', None),
                ('resistanceBeforeSeal', None),
                ('resistanceBeforeBreakin', None),
                ('offsetBeforeSeal', None),
                ('attemptedBreakin', False),
                ('breakinSuccessful', None),
                ('spontaneousBreakin', None),
                ('initialBaselineCurrent', None),
                ('initialBaselinePotential', None),
                ('wholeCellStartTime', None),
                ('wholeCellStopTime', None),
                ('wholeCellPosition', None),
                ('resealResistance', None),
                ('resistanceAfterBlowout', None),
                ('offsetAfterBlowout', None),
                ('complete', False),
            ]
        )

    def patchRecord(self):
        if self._patchRecord is None:
            self._resetPatchRecord()
        return self._patchRecord

    def setCell(self, cell, target=True):
        self.closeCell()
        self.cell = cell
        if target:
            self.pipetteDevice.setTarget(cell.position.mapped_to('global').coordinates)

    def newCell(self):
        try:
            from acq4_automation.feature_tracking.cell import Cell
            self.closeCell()
            self.cell = Cell(Point(self.pipetteDevice.targetPosition(), 'global'))
        except ImportError:
            self.logger.exception(
                "Cell-based features are unavailable without the acq4_automation package",
            )

    def closeCell(self):
        if self.cell is not None:
            self.cell.enableTracking(False)
            self.previousCells.append(self.cell)
            self.cell = None

    def finishPatchRecord(self):
        if self._patchRecord is None:
            return
        self._patchRecord['complete'] = True
        self.sigPatchAttemptFinished.emit(self, self._patchRecord)
        self._patchRecord = None

    def pressureChanged(self, dev, source, pressure):
        self.sigPressureChanged.emit(self, source, pressure)
        self.emitNewEvent(
            'pressure_changed', OrderedDict([('source', source), ('pressure', pressure)])
        )

    def sonicationChanged(self, state: str):
        self.emitNewEvent('sonication_changed', {'state': state})

    def setSelected(self):
        pass

    def setState(self, state, setActive=True, **config):
        """Attempt to set the state (out, bath, seal, whole cell, etc.) of this patch pipette.

        The actual resulting state is returned.
        """
        if setActive:
            self.setActive(True)
        return self._stateManager.requestStateChange(state, **config)

    def listStates(self):
        """Return a list of all known state names this pipette can be set to."""
        return self._stateManager.listStates()

    def _setState(self, state, oldState):
        """Called by state manager when state has changed."""
        self._writeStateFile()
        self.emitNewEvent('state_change', OrderedDict([('state', state), ('old_state', oldState)]))
        self.sigStateChanged.emit(self, state, oldState)

    def _writeStateFile(self):
        state = {
            'state': self._stateManager.getState().stateName,
            'active': self.active,
            'calibrated': self.calibrated,
            'broken': self.broken,
        }
        self.writeConfigFile(state, 'last_state')

    def getState(self):
        return self._stateManager.getState()

    def breakIn(self):
        """Rupture the cell membrane using negative current pulses.

        * -2 psi for 3 sec or until rupture
        * -4, -6, -8 psi if needed
        * longer wait time if needed
        """

    def _pipetteCalibrationChanged(self):
        self.calibrated = True
        self.emitNewEvent('pipette_calibrated')

    def _manipulatorTransformChanged(self, dev, *args):
        pos = np.array(self.pipetteDevice.globalPosition())
        if self._lastPos is None or np.linalg.norm(pos - self._lastPos) > 1e-6:
            self._lastPos = pos
            self.emitNewEvent('pipette_transform_changed', {'globalPosition': tuple(pos)})

    def setActive(self, active):
        if self.active == active:
            return
        self.active = active
        self.sigActiveChanged.emit(self, active)
        self.emitNewEvent('active_changed', {'active': active})

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return PatchPipetteDeviceGui(self, win)

    def clampStateChanged(self, state):
        self.emitNewEvent('clamp_state_change', state)

    def _initStateManager(self):
        # allow external modification of state manager class
        self._stateManager = self.defaultStateManagerClass(self)
        self.setState('out')

    def stateManager(self):
        return self._stateManager

    def quit(self):
        self._releaseControls()
        if self.clampDevice:
            self.clampDevice.enableTestPulse(False, block=True)
        if getattr(self, '_stateManager', None) is not None:
            self._stateManager.quit()

    # --------------------------------------------------------- control surface bindings

    #: Background drawn behind a text-capable key while its state is the active one.
    activeStateColor = '#0d5c2a'

    def _setupControls(self, config):
        """Acquire and bind every control named in the ``controls:`` config block.

        A missing or empty block is a no-op, so a patch pipette on a rig with no control
        surface costs nothing. Runs at the end of :meth:`PatchPipette.__init__`, after the
        state manager exists, so that the first paint shows the state the device is really
        in.

        Parameters
        ----------
        config : dict
            This device's configuration.
        """
        conf = config.get('controls', None)
        if not conf:
            return
        if not isinstance(conf, dict):
            raise TypeError(
                f"{self.name()}: 'controls' must be a dict of named control specs, not "
                f"{type(conf).__name__}"
            )
        try:
            for name, spec in conf.items():
                control = acquireControlFromConfig(spec, owner=self)
                self._boundControls[name] = control
                self.bindControl(name, control, spec)
        except Exception:
            # Release controls claimed so far: a device whose construction raises is never
            # quit(), and a claimed control cannot be acquired again until released.
            self._releaseControls()
            raise
        if self._stateControls:
            self.sigStateChanged.connect(self._controlStateChanged)
            self._paintStateControls()

    def controlNames(self) -> list:
        """Return the action names accepted in the ``controls:`` config block.

        These are the state names the state machine knows -- :meth:`listStates` -- so that
        a state added to the registry is bindable with no change here. Also includes
        method-call actions like ``'newPipette'``.
        """
        return self.listStates() + ['newPipette']

    def bindControl(self, name, control, conf):
        """Give *control* the behaviour named *name* in the ``controls:`` config block.

        Dispatch is open: a subclass overrides this, handles its own names and delegates
        anything else back here with ``PatchPipette.bindControl(self, name, control, conf)``.

        Parameters
        ----------
        name : str
            The key this control was declared under; a state name. It is also the key's
            default label; ``label`` overrides that.
        control : Control
            The control, already acquired for this device.
        conf : dict
            The whole config entry, so that an action can read its own options (this
            action's ``setActive`` and ``label``) alongside the address.

        Raises
        ------
        ValueError
            If *name* is not an action this device offers, or if *control* cannot drive it.
        """
        opts = conf if isinstance(conf, dict) else {}
        if name in self.listStates():
            self._bindStateButton(name, control, opts)
            return
        if name == 'newPipette':
            self._bindNewPipetteButton(control, opts)
            return
        raise ValueError(
            f"{self.name()}: unknown control name {name!r} in the 'controls:' config block;"
            f" {type(self).__name__} accepts {sorted(self.controlNames())}"
        )

    def _bindStateButton(self, name, control, opts):
        """Bind a press of *control* to a request for state *name*.

        Raises
        ------
        ValueError
            If *control* reports no press input, so that a fader or a non-pressable dial in
            the config is a startup error rather than a button that silently never fires.
        """
        caps = control.capabilities()
        if not caps['input'].get('press'):
            raise ValueError(
                f"{self.name()}: state control {name!r} is bound to {control}, which reports"
                f" no press input; requesting a state needs a control that can be pressed"
            )
        label = controlLabelFromConfig(opts, name, self.name(), name)
        self._stateControls[control] = {
            'state': name,
            'label': label,
            'control': control,
            'setActive': bool(opts.get('setActive', True)),
            'indicator': self._resolveStateIndicator(name, label, control, caps),
        }
        control.sigPressed.connect(self._stateButtonPressed)

    def _bindNewPipetteButton(self, control, opts):
        """Bind a press of *control* to :meth:`newPipette` and draw its label once.

        Raises
        ------
        ValueError
            If *control* reports no press input.
        Exception
            Whatever *control* raises if it declares text output but fails to draw the
            label.
        """
        caps = control.capabilities()
        if not caps['input'].get('press'):
            raise ValueError(
                f"{self.name()}: 'newPipette' control is bound to {control}, which reports"
                f" no press input"
            )
        label = controlLabelFromConfig(opts, 'newPipette', self.name(), 'new pipette')
        if hasattr(control, 'setText') and caps['output'].get('text'):
            control.setText(label)
        control.sigPressed.connect(self._newPipettePressed)

    def _newPipettePressed(self, control):
        """Call :meth:`newPipette` on the GUI thread, logging any exception instead of raising."""
        try:
            self.newPipette()
        except Exception:
            self.logger.exception(f"{self.name()}: newPipette control failed")

    def _resolveStateIndicator(self, name, label, control, caps):
        """Work out once how *control* can show state *name* and whether it is active.

        Output belongs to each control surface rather than to a generic interface, so this
        asks the control what it offers: a Stream Dock key has a little display and takes
        ``setText``, an X-Keys key has two LEDs and takes ``setBacklight``. Having the
        method is not proof this particular control has the output -- one control class
        covers a surface's keys *and* its dials -- so each candidate is tried once, on the
        inactive state, and one that refuses is passed over.

        Settling it here means :meth:`_paintStateControls` is a call rather than a decision,
        and a control that can show nothing is said so once instead of on every transition.
        A key that cannot indicate anything still requests its state.

        Parameters
        ----------
        name : str
            The state this control requests, for the log line only.
        label : str
            The text to draw: the entry's ``label``, or *name* by default. The text-capable
            indicator closes over it and redraws it on every repaint, so highlighting the
            active key changes its background and never its label.
        control : Control
            The control, already acquired for this device.
        caps : dict
            *control*'s capabilities, as already read by the caller.

        Returns
        -------
        callable or None
            ``indicator(active: bool)``, or None if this control can show nothing.
        """
        candidates = []
        if hasattr(control, 'setText') and caps['output'].get('text'):
            candidates.append(
                lambda active: control.setText(
                    label, background=self.activeStateColor if active else None
                )
            )
        if hasattr(control, 'setBacklight'):
            candidates.append(lambda active: control.setBacklight(int(active), int(active)))
        if hasattr(control, 'setColor'):
            # magenta rather than a green: that is what a blue and a red LED lit together
            # look like, and it is the one "on" colour both kinds of key can show
            candidates.append(lambda active: control.setColor('m' if active else 'k'))
        for indicator in candidates:
            try:
                indicator(False)
            except UnsupportedControlFeature:
                continue  # the class offers it, this control does not
            return indicator
        self.logger.warning(
            f"{self.name()}: {control} will not show state {name!r} or whether it is active;"
            f" it offers no output this device knows how to drive. The button still requests"
            f" the state."
        )
        return None

    def _stateButtonPressed(self, control):
        """Request the state bound to *control*. Always runs on the GUI thread.

        No Panic Lock check of its own: :meth:`setState` goes through
        :meth:`~acq4.devices.PatchPipette.statemanager.PatchPipetteStateManager.requestStateChange`,
        whose funnel checks ``globalHalt`` before any side effect ("Panic Lock Spec."
        6.1/10.1). A refused transition lands in the log below, because a button press has
        no caller to raise at.
        """
        binding = self._stateControls.get(control)
        if binding is None:
            return
        try:
            self.setState(binding['state'], setActive=binding['setActive'])
        except Exception:
            self.logger.exception(
                f"{self.name()}: control-driven request for state {binding['state']!r} failed"
            )

    def _controlStateChanged(self, dev, newState, oldState):
        """Repaint the bound keys when the state machine reports a transition."""
        self._paintStateControls(newState)

    def _paintStateControls(self, activeState=None):
        """Highlight the key whose state is active, and unhighlight the rest.

        *activeState* is the state name to treat as active; when it is None the state
        machine is asked, which is what the first paint and any out-of-band repaint want.
        A control whose indicator could not be resolved is skipped. A refused write is
        logged and the remaining keys are still painted: a half-painted surface is better
        than a surface abandoned mid-repaint.
        """
        if activeState is None:
            job = self.getState()
            activeState = None if job is None else job.stateName
        for binding in self._stateControls.values():
            indicator = binding['indicator']
            if indicator is None:
                continue
            try:
                indicator(binding['state'] == activeState)
            except Exception:
                self.logger.exception(
                    f"{self.name()}: failed to paint state {binding['state']!r} on "
                    f"{binding['control']}"
                )

    def _releaseControls(self):
        """Release every control claimed from the ``controls:`` config block.

        Called from :meth:`quit`, so that a re-created device or a reopened window can claim
        the same controls again -- :meth:`Control.acquire` is strictly once until released.
        Signals are disconnected wholesale: acquisition is exclusive, so nothing else is
        listening to a control this device owns.
        """
        for control in getattr(self, '_boundControls', {}).values():
            for signal in (
                control.sigPressed,
                control.sigReleased,
                control.sigMoved,
                control.sigTouched,
            ):
                try:
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass
            try:
                control.release()
            except Exception:
                self.logger.exception(f"{self.name()}: failed to release {control}")
        if getattr(self, '_stateControls', None):
            try:
                self.sigStateChanged.disconnect(self._controlStateChanged)
            except (TypeError, RuntimeError):
                pass
        self._boundControls = {}
        self._stateControls = {}

    def goHome(self, speed, **kwds):
        self.setState('out')
        return self.pipetteDevice.goHome(speed, **kwds)

    def _pipetteMoveStarted(self, pip, pos):
        self.sigMoveStarted.emit(self)
        self.emitNewEvent('move_start', {'position': tuple(pos)})

    def _pipetteMoveRequested(self, pip, pos, speed, opts):
        event = {'position': tuple(pos), 'speed': speed, 'opts': repr(opts)}
        if 'name' in opts:
            event['name'] = opts['name']
        self.emitNewEvent(
            'move_requested',
            event,
        )

    def _pipetteMoveFinished(self, pip, pos):
        self.sigMoveFinished.emit(self, pos)
        self.emitNewEvent('move_stop', {'position': [pos[0], pos[1], pos[2]]})

    def _pipetteTargetChanged(self, pip, pos):
        self.sigTargetChanged.emit(self, pos)
        self.emitNewEvent('target_changed', {'target_position': [pos[0], pos[1], pos[2]]})

    def _autoBiasChanged(self, clamp, enabled, target):
        self.emitNewEvent('auto_bias_change', {'enabled': enabled, 'target': target})

    def requestFullTestPulseData(self, token) -> None:
        """Ask that test_pulse events carry the full PatchClampTestPulse object.

        `token` identifies the subscriber and is what releaseFullTestPulseData()
        takes back; any hashable will do. Idempotent per token.
        """
        self._fullTestPulseSubscribers.add(token)

    def releaseFullTestPulseData(self, token) -> None:
        """Withdraw `token`'s request. Full data keeps flowing while any other
        subscriber holds one. Releasing an unknown token is a no-op, so a
        recorder's idempotent stop() can call it freely."""
        self._fullTestPulseSubscribers.discard(token)

    def emitsFullTestPulseData(self) -> bool:
        return bool(self._fullTestPulseSubscribers)

    def _testPulseFinished(self, clamp, result: PatchClampTestPulse):
        data = result.analysis
        if self._fullTestPulseSubscribers:
            data = {'full_test_pulse': result, **data}  # copy it so we don't modify the original
        self.emitNewEvent('test_pulse', data)

    def eventLog(self) -> list:
        """Return the in-memory list of semantically meaningful events since the last newPatchAttempt()."""
        return list(self._logEvents)

    def emitNewEvent(self, eventType, eventData=None):
        newEv = OrderedDict(
            [
                ('device', self.name()),
                ('event_time', ptime.time()),
                ('event', eventType),
            ]
        )
        if eventData is not None:
            newEv.update(eventData)
        if eventType in LOG_EVENT_TYPES:
            with self._logLock:
                self._logEvents.append(dict(newEv))
        self.sigNewEvent.emit(self, newEv)
