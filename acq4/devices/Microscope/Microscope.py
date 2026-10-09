import collections

import numpy as np

import pyqtgraph as pg
from acq4.Manager import getManager
from acq4.devices.ControlSurface import UnsupportedControlFeature, acquireControlFromConfig
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from acq4.modules.Camera import CameraModuleInterface
from acq4.motion import MoveSpec
from acq4.panic import GlobalHaltException
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.acq4_typing import Number
from acq4.util.imaging import Frame
from acq4.util.surface import find_surface
from acq4.util.task import MultiFuture, asynch, asynch_with_qt_signals, FutureButton
from acq4.util.ui.ZPositionWidget import ZPositionWidget
from coorx import TTransform
from pyqtgraph.units import µm

Ui_Form = Qt.importTemplate('.deviceTemplate')

#: Keys of a ``presets:`` entry that name something other than a device to configure.
#: ``objective`` is handled specially by :meth:`Microscope.loadPreset`; ``control`` (and
#: its deprecated spelling ``hotkey``) binds the preset to a control surface.
RESERVED_PRESET_KEYS = frozenset({'objective', 'control', 'hotkey'})


class Microscope(Device, OptomechDevice):
    """
    The Microscope device class has several purposes:

    * Acts as a parent for imaging and photostimulation devices
    * Account for differences in magnification, focal plane, and xy offset between objectives
        * Maintains list of objective slots (most scopes have 2-5 slots)
        * For each slot, maintains a list of possible objectives that may be found there
          (this allows the experimenter to change the objective at a certain slot
          during the experiment)
        * Support for automatically selecting the correct objective position based on a Switch device
        * Each objective has an offset and scale factor associated with it. This transformation is communicated
          automatically to all rigidly-connected child devices.
    * Manage multiple parent stage devices (such as independent focus / xy stages)
    * Manage attached light + filter devices
    * Track the focus depth of sample surface

    Configuration options:

    * **presets** (dict, optional): Named device states that can be applied together
      (see :func:`loadPreset`). Each preset maps device names to the state passed to that
      device's ``loadPreset`` method. Two keys are reserved: 'objective' selects an
      objective switch position, and 'control' binds the preset to a control-surface
      button (see :func:`~acq4.devices.ControlSurface.acquireControlFromConfig`; the
      surface device must be declared before the microscope). The old
      ``hotkey: {'device': ..., 'key': ...}`` spelling is still accepted, deprecated.

    * **controls** (dict, optional): Control-surface buttons bound to this microscope's
      objective lift/dip actions (see :meth:`moveLift` and :meth:`moveDip`). The block is a
      dict of *named actions*; each value is a control address as understood by
      :func:`~acq4.devices.ControlSurface.acquireControlFromConfig`, plus any options that
      action takes. Two names are accepted -- ``lift`` and ``dip`` (see
      :meth:`controlNames`) -- and each must be bound to a pressable button. Pressing it
      moves focus to the height stored for the *currently selected objective*, captured
      from the device rack's "Set Lift" / "Set Dip" buttons and persisted per objective, so
      neither destination goes stale when the objective is changed or driven around while
      raised. A height that has never been set is refused loudly: the press raises, and
      where the button can draw text its label says ``(unset)``.

      Per-action options:

      label : str
          Text drawn on the button, where the button can draw text. Defaults to the
          capitalized action name (``'Lift'`` / ``'Dip'``).
      speed : float or str
          Speed for the move, as accepted by :meth:`acq4.devices.Stage.Stage.Stage.move`.
          Defaults to ``'fast'``.

      What the button shows is resolved once, at bind time, from what that control offers:
      a button with a display shows its label, backed by
      :attr:`liftDipActiveBackground` while focus is within
      :attr:`liftDipIndicatorTolerance` of that action's height; a button with only LEDs
      lights while focus is at that height; a button with no output at all still moves the
      objective, and says once in the log that it will not indicate anything.

    * **initialPreset** (str, optional): Name of a preset from *presets* to load once at
      startup. The preset is applied after all devices have finished configuring, so it
      may refer to devices defined later in the config file. Note that this happens after
      each device has set up its own startup state (e.g. a light source's *initialState*),
      so the preset wins where the two overlap.

    A control surface must be declared *before* the microscope in ``devices.cfg``, matching
    the existing ``parentDevice:`` convention -- devices are constructed in file order, and
    a control address is resolved by looking its surface up by name.

    Example configuration::

        Microscope:
            driver: 'Microscope'
            parentDevice: 'Stage'
            initialPreset: 'brightfield'
            presets:
                brightfield:
                    LEDs:
                        channel: 'IR'
                GFP:
                    LEDs:
                        channel: 'Blue'
                    control:
                        device: 'PIKeyboard'
                        type: 'button'      # default
                        page: 0             # default
                        key: [1, 0]
            controls:
                lift: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [0, 4]}
                dip: {'device': 'Dock', 'type': 'button', 'page': 0, 'key': [1, 4], 'speed': 'slow'}
            objectives:
                # one block per objective-switch position; see *objectives* above
                0:
                    40x:
                        name: '40x 0.75na Achroplan'
                        scale: 0.0835
    """

    sigObjectiveChanged = Qt.Signal(object)  ## (objective, lastObjective)
    sigLightChanged = Qt.Signal(object, object)  # self, lightName
    sigObjectiveListChanged = Qt.Signal()
    sigSurfaceDepthChanged = Qt.Signal(object)
    sigObjectiveHeightsChanged = Qt.Signal(object)  # objective whose lift/dip height changed

    #: Action names accepted in the ``controls:`` config block.
    _LIFT_DIP_ACTIONS = ('lift', 'dip')

    #: Distance (m) within which the focus depth counts as being *at* a configured lift or
    #: dip height, for the purpose of indicating it on a control-surface button. Only ever
    #: used for the indicator; nothing decides whether to move from it.
    liftDipIndicatorTolerance = 5 * µm

    #: Background drawn behind a lift/dip button's label while the focus depth is at that
    #: button's configured height, on a button that can draw text.
    liftDipActiveBackground = '#7f5000'

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self.presets = config.get('presets', {})
        self._initialPreset = config.get('initialPreset', None)
        if self._initialPreset is not None and self._initialPreset not in self.presets:
            raise ValueError(
                f"Microscope {name} has initialPreset '{self._initialPreset}', which is not a"
                f" configured preset (options are {', '.join(self.presets) or 'none'})"
            )
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.switchDevice = None
        self.currentSwitchPosition = None
        self.currentObjective = None
        self._focusDevice = None
        self._positionDevice = None
        self._surfaceDepth = None

        self.objectives = collections.OrderedDict()
        ## Format of self.objectives is:
        ## {
        ##    switchPosition1: {objName1: objective1, objName2: objective, ...},
        ##    switchPosition2: {objName1: objective1, objName2: objective, ...},
        ## }

        for slot_name, objs in config['objectives'].items():  ## Set default values for each objective
            self.objectives[slot_name] = collections.OrderedDict()
            for obj_name, o in objs.items():
                obj = Objective(o, self, (slot_name, obj_name))
                self.objectives[slot_name][obj_name] = obj
                # obj.sigTransformChanged.connect(self.objectiveTransformChanged)

        ## Keep track of the objective currently in use for each position
        ## Format is: { switchPosition1: objective1,  ... }
        self.selectedObjectives = collections.OrderedDict(
            [(i, list(self.objectives[i].values())[0]) for i in self.objectives]
        )
        for obj in self.selectedObjectives.values():
            self.addSubdevice(obj)

        ## if there is a light source, configure it here
        if 'lightSource' in config:
            self.lightSource = dm.getDevice(config['lightSource'])
            self.lightSource.sigLightChanged.connect(self._lightChanged)
        else:
            self.lightSource = None

        ## If there is a switch device, configure it here
        if 'objectiveSwitch' in config:
            self.switchDevice = dm.getDevice(config['objectiveSwitch'][0])  ## Switch device
            self.objSwitchId = config['objectiveSwitch'][1]  ## Switch ID
            self.switchDevice.sigSwitchChanged.connect(self.objectiveSwitchChanged)
            try:
                self.objectiveSwitchChanged()
            except:
                self.logger.exception("Could not set initial objective state:")
        else:
            self.switchDevice = None
            firstObj = next(iter(self.objectives))
            self.objectiveIndexChanged(firstObj)

        cal = self.readConfigFile('calibration')
        if 'surfaceDepth' in cal:
            self.setSurfaceDepth(cal['surfaceDepth'])

        dm.declareInterface(name, ['microscope'], self)

        # Preset control-surface buttons. These are claimed here rather than in ScopeGUI
        # so that a preset key works whether or not the device rack is open, and so that
        # reopening the rack does not try to claim the same control twice.
        self._presetControls = {}  # Control -> preset name
        for presetName, presetConf in self.presets.items():
            controlConf = presetConf.get('control')
            if controlConf is None and 'hotkey' in presetConf:
                controlConf = {'hotkey': presetConf['hotkey']}
            if controlConf is None:
                continue
            control = acquireControlFromConfig(controlConf, owner=self)
            self._presetControls[control] = presetName
            control.sigPressed.connect(self.handlePresetControl)

        # Lift/dip control-surface buttons, from the `controls:` block.
        self._boundControls = {}  # config name -> Control
        self._liftDipControls = {}  # Control -> binding dict
        self._setupControls(config)

        if self._initialPreset is not None:
            # a preset may refer to devices that are configured after this one, so wait until
            # the manager has finished loading the whole config before applying it
            dm.sigConfigChanged.connect(self._loadInitialPreset)

    def quit(self):
        self._releaseControls()

    def _loadInitialPreset(self):
        # only ever fires once, on the first config load after this device was created
        self.dm.sigConfigChanged.disconnect(self._loadInitialPreset)
        name = self._initialPreset
        asynch(self.loadPreset, detach=True, raise_errors=f"Error loading initial preset {name}")(name)

    def objectiveSwitchChanged(self, sw=None, change=None):
        ## Called when the switch device has changed, NOT when the user has selected a different objective.
        ## *change* looks like { switchId1: newValue, switchId2: newValue, ... }
        if sw is None:
            change = {self.objSwitchId: self.switchDevice.getSwitch(self.objSwitchId)}

        if self.objSwitchId not in change:  ## the switch(es) that changed are not relevant to this device
            return
        state = str(change[self.objSwitchId])
        self.objectiveIndexChanged(state)

    def setObjectiveIndex(self, index):
        """Selects the objective currently in position *index*

        This method is called when the user selects an objective index from the manager UI."""
        if self.switchDevice is not None and hasattr(self.switchDevice, 'setSwitch'):
            self.switchDevice.setSwitch(self.objSwitchId, int(index))
        else:
            self.objectiveIndexChanged(index)

    def objectiveIndexChanged(self, index):
        # called when the objective index has changed.
        index = str(index)
        if index not in self.selectedObjectives:
            raise ValueError(
                f"Requested invalid objective switch position: {index} (options are {', '.join(list(self.objectives.keys()))})"
            )

        ## determine new objective, return early if there is no change
        ## NOTE: it is possible in some cases for the objective to have changed even if the index has not.
        with self.lock:
            lastObj = self.currentObjective
            self.currentSwitchPosition = index
            self.currentObjective = self.getObjective()
            if self.currentObjective == lastObj:
                return

        self.setCurrentSubdevice(self.currentObjective)
        self.sigObjectiveChanged.emit((self.currentObjective, lastObj))
        self.sigGeometryChanged.emit(self)

    def getGeometry(self, name=None):
        objective = self.getObjective()
        if objective is None:
            return None
        return objective.getGeometryForMicroscope(name=self.geometryCacheKey)

    def getObjective(self) -> "Objective | None":
        """Return the currently active Objective."""
        with self.lock:
            if self.currentSwitchPosition not in self.selectedObjectives:
                return None
            return self.selectedObjectives[self.currentSwitchPosition]

    def listObjectives(self):
        """
        Return a list of available objectives. (one objective returned per switch position)
        """
        with self.lock:
            return list(self.selectedObjectives.values())

    def loadPreset(self, name):
        conf = self.presets[name]
        tasks = []
        for dev_name, state in conf.items():
            if dev_name == "objective":
                self.setObjectiveIndex(state)
            elif dev_name not in RESERVED_PRESET_KEYS:
                dev = self.dm.getDevice(dev_name)
                if hasattr(dev, "loadPreset"):
                    tasks.append(asynch(dev.loadPreset)(state))
        for task in tasks:
            task.wait()

    def handlePresetControl(self, control):
        """Load the preset bound to *control*.

        The control surface only signals a press on a claimed control, so unlike the old
        key-callback path there is no key list to unpack and no press/release to filter.
        """
        name = self._presetControls[control]
        asynch(self.loadPreset, detach=True, raise_errors=f"Error loading preset {name}")(name)

    def deviceInterface(self, win):
        iface = ScopeGUI(self, win)
        iface.objectiveChanged((self.currentObjective, None))
        return iface

    def physicalTransform(self, subdev=None):
        tr = TTransform(offset=self.deviceTransform().offset)
        dev = self.getSubdevice(subdev)
        if dev is None:
            return tr
        else:
            return tr * dev.physicalTransform()

    def selectObjective(self, obj):
        ##Set the currently-active objective for a particular switch position
        ##This is _not_ the same as objectiveIndexChanged.
        index = obj.key()[0]
        with self.lock:
            self.removeSubdevice(self.selectedObjectives[index])
            self.selectedObjectives[index] = obj
            self.addSubdevice(obj)
        self.objectiveIndexChanged(self.currentSwitchPosition)  # update self.currentObjective, send signals (if needed)
        self.sigObjectiveListChanged.emit()

    def _allObjectives(self):
        ## used by (preferrably only) GUI interface
        return self.objectives

    def _lightChanged(self, light, name):
        self.sigLightChanged.emit(self, name)

    def cameraModuleInterface(self, win):
        """Return an object to interact with camera module.
        """
        return ScopeCameraModInterface(self, win)

    def getFocusDepth(self):
        """Return the z-position of the focal plane.

        This method requires a device that provides focus position feedback.
        """
        return self.mapToGlobal((0, 0, 0))[2]

    def getDefaultImager(self):
        name = self.config.get('defaultImager', None)
        if name is None:
            cameras = self.dm.listInterfaces("camera")
            if len(cameras) == 0:
                raise RuntimeError("No camera devices available.")
            name = cameras[0]
        return self.dm.getDevice(name)

    def getZStack(self, imager: "Device", z_range, name="z stack") -> list[Frame]:
        """Acquire a z-stack of images using the given imager.

        The z-stack is returned as frames.
        """
        from acq4.util.imaging.sequencer import acquire_z_stack

        return acquire_z_stack(imager, *z_range, name=name)

    def findSurfaceDepth(
        self, imager: "Device", searchDistance=200 * µm, searchStep=5 * µm, returnStack=False
    ) -> float | tuple[float, list[Frame]]:
        """Set the surface of the sample based on how focused the images are."""
        z_range = (
            self.getSurfaceDepth() + searchDistance,
            self.getSurfaceDepth() - searchDistance,
            searchStep,
        )
        z_stack: list[Frame] = self.getZStack(imager, z_range, name="finding surface")
        threshold = self.config.get('surfaceDetectionPercentileThreshold', 96)
        if (idx := find_surface(z_stack, threshold)) is not None:
            depth = z_stack[idx].mapFromFrameToGlobal([0, 0, 0])[2]
            self.setSurfaceDepth(depth)
            self.setFocusDepth(depth, name=f"{self.name()} focus to detected surface").wait()
            if returnStack:
                return depth, z_stack
            return depth
        raise ValueError("Could not find surface")

    def getSurfaceDepth(self) -> Number:
        """Return the z-position of the sample surface as marked by the user.
        """
        return self._surfaceDepth

    def setSurfaceDepth(self, depth):
        self._surfaceDepth = depth
        self.sigSurfaceDepthChanged.emit(depth)
        self.writeCalibration()

    def globalPosition(self):
        """Return the global position of the scope's center axis at the focal plane.
        """
        return self.mapToGlobal(np.array((0, 0, 0)))

    def setGlobalPosition(self, pos, speed='fast', name=None):
        return self.dm.move(MoveSpec(self, pos, speed=speed), name=name)

    def moveToGlobalNoPlanning(self, pos, speed='fast', name=None):
        """Move the microscope such that its center axis is at a specified global position.

        If *pos* is a 3-element vector, then this method will also attempt to set the focus depth
        accordingly.

        Return a MoveFuture instance.
        """
        pos = np.asarray(pos)
        positionDevice = self.positionDevice()
        focusDevice = self.focusDevice()

        if len(pos) == 3 and focusDevice is not positionDevice:
            z = pos[2]
            dif = z - self.getFocusDepth()
            fdpos = focusDevice.globalPosition()
            fdpos[2] += dif
            zFuture = focusDevice.moveToGlobalNoPlanning(fdpos, speed, name=f'{name} Z')
            pos = pos[:2]
        else:
            zFuture = None

        if len(pos) == 2:
            pos = list(pos) + [self.getFocusDepth()]

        # Determine how to move the xy(z) stage to reach the new center position
        gpos = self.globalPosition()
        sgpos = positionDevice.globalPosition()
        sgpos2 = sgpos + (pos - gpos)
        xyFuture = positionDevice.moveToGlobalNoPlanning(sgpos2, speed, name=f'{name} XY')
        if zFuture is None:
            return xyFuture
        else:
            return MultiFuture([zFuture, xyFuture], name=f'{self.name()} {name} XY+Z')

    def writeCalibration(self):
        cal = {'surfaceDepth': self.getSurfaceDepth()}
        self.writeConfigFile(cal, 'calibration')

    def focusDevice(self):
        if self._focusDevice is None:
            if 'focusDevice' in self.config:
                # check config first
                self._focusDevice = getManager().getDevice(self.config['focusDevice'])
            else:
                # if nothing was specified, then use the first parent stage with z positioning
                p = self
                while True:
                    if p is None or isinstance(p, Stage) and p.capabilities()['setPos'][2]:
                        self._focusDevice = p
                        break
                    p = p.parentDevice()
        return self._focusDevice

    def moveDip(self, speed='fast'):
        """Move to the dip height configured for the current objective."""
        obj = self.getObjective()
        if obj is None:
            raise RuntimeError("No objective selected")
        z = obj.getDipHeight()
        if z is None:
            raise RuntimeError(f"No dip height set for objective '{obj.name()}'")
        return self.setFocusDepth(z, speed=speed, name=f"{self.name()} move to dip height")

    def moveLift(self, speed='fast'):
        """Move to the lift height configured for the current objective."""
        obj = self.getObjective()
        if obj is None:
            raise RuntimeError("No objective selected")
        z = obj.getLiftHeight()
        if z is None:
            raise RuntimeError(f"No lift height set for objective '{obj.name()}'")
        return self.setFocusDepth(z, speed=speed, name=f"{self.name()} move to lift height")

    # --------------------------------------------------------- control surface bindings

    def _setupControls(self, config):
        """Acquire and bind every control named in the ``controls:`` config block.

        A missing or empty block is a no-op, so a microscope on a rig with no control
        surface costs nothing.

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
            # A device whose construction raises is never quit(), so anything already
            # claimed here -- including this device's preset buttons -- would stay claimed
            # for the life of the process, and acquisition is strictly once until released.
            self._releaseControls()
            raise
        if self._liftDipControls:
            for signal in (
                self.sigGlobalTransformChanged,
                self.sigObjectiveChanged,
                self.sigObjectiveHeightsChanged,
            ):
                signal.connect(self._liftDipStateChanged)
            # Paint once the rest of the config has been constructed and the focus device
            # can be asked where it is.
            Qt.QTimer.singleShot(0, self._paintLiftDipControls)

    def controlNames(self) -> list:
        """Return the action names accepted in the ``controls:`` config block."""
        return list(self._LIFT_DIP_ACTIONS)

    def bindControl(self, name, control, conf):
        """Give *control* the behaviour named *name* in the ``controls:`` config block.

        Parameters
        ----------
        name : str
            The key this control was declared under.
        control : Control
            The control, already acquired for this device.
        conf : dict
            The whole config entry, so that an action can read its own options (a button's
            ``label``, ``speed``) alongside the address.

        Raises
        ------
        ValueError
            If *name* is not an action this device offers, or if *control* cannot drive it.
        """
        if name in self._LIFT_DIP_ACTIONS:
            self._bindLiftDipButton(name, control, conf)
            return
        raise ValueError(
            f"{self.name()}: unknown control name {name!r} in the 'controls:' config "
            f"block; {type(self).__name__} accepts {sorted(self.controlNames())}"
        )

    def _bindLiftDipButton(self, name, control, conf):
        """Bind a button to :meth:`moveLift` or :meth:`moveDip`.

        Two separate buttons rather than one toggle, and both destinations read from the
        objective rather than captured at press time: each press is then an idempotent move
        to a named, persisted absolute height, with no "where we came from" to go stale
        while the objective is raised, swapped or driven around. The price is that an
        unconfigured height has nowhere to go, which is refused rather than guessed -- see
        :meth:`_liftDipPressed`.

        Raises
        ------
        ValueError
            If *control* is not a button, or cannot report a press.
        """
        if control.type != 'button':
            raise ValueError(
                f"{self.name()}: {name!r} is bound to {control}, which is a "
                f"{control.type!r} and not a button"
            )
        caps = control.capabilities()
        if not caps['input'].get('press'):
            raise ValueError(
                f"{self.name()}: {name!r} is bound to {control}, which does not report presses"
            )
        label = str(conf.get('label', name.capitalize()))
        binding = {
            'name': name,
            'control': control,
            'label': label,
            'speed': conf.get('speed', 'fast'),
            'painter': self._liftDipPainter(name, control, label),
            'state': None,  # last painted (configured, active); None means never painted
        }
        self._liftDipControls[control] = binding
        control.sigPressed.connect(self._liftDipPressed)

    def _liftDipPainter(self, name, control, label):
        """Work out once how *control* can show the state of action *name*.

        Output belongs to each control surface rather than to a generic interface, so this
        asks the control what it offers. A button with a display gets the label and a
        background; a button with only LEDs gets lit or unlit, which is two states for
        three, so it reports "focus is at this height" and nothing about whether the height
        exists at all. Having the method is not proof the control has the output -- one
        control class covers a surface's keys *and* its dials, and an X-Keys jog wheel has
        no LEDs -- so each LED candidate is tried once, on the "off" state the button starts
        in, and one that refuses is passed over.

        Returns
        -------
        callable or None
            ``painter(configured, active)``, or None if this control can show nothing.
        """
        caps = control.capabilities()
        if hasattr(control, 'setText') and caps['output'].get('text'):

            def paintText(configured, active):
                if not configured:
                    control.setText(f'{label}\n(unset)')
                else:
                    control.setText(
                        label, background=self.liftDipActiveBackground if active else None
                    )

            return paintText

        candidates = []
        if hasattr(control, 'setBacklight'):
            candidates.append(
                lambda configured, active: control.setBacklight(int(active), int(active))
            )
        if hasattr(control, 'setColor'):
            candidates.append(lambda configured, active: control.setColor('m' if active else 'k'))
        for painter in candidates:
            try:
                painter(False, False)
            except UnsupportedControlFeature:
                continue  # the class offers it, this control does not
            return painter

        self.logger.warning(
            f"{self.name()}: {control} will not show anything for {name!r}; it offers no "
            f"output this device knows how to drive. The button still moves the objective."
        )
        return None

    def _liftDipStateChanged(self, *args):
        """Repaint lift/dip buttons after a focus move, objective swap or height change."""
        self._paintLiftDipControls()

    def _paintLiftDipControls(self):
        """Paint every bound lift/dip button, skipping the ones that have not changed.

        Focus updates arrive far faster than a two-state indicator changes, so the last
        painted state is compared rather than rate-limited by a timer: driving focus through
        a configured height costs two hardware writes, and driving it anywhere else costs
        none.
        """
        if not self._liftDipControls:
            return
        obj = self.getObjective()
        try:
            focus = self.getFocusDepth()
        except Exception:
            # No focus feedback (no parent stage with z, or hardware not answering) is not a
            # reason to fail a repaint; the label still wants drawing.
            focus = None
        for binding in self._liftDipControls.values():
            height = None
            if obj is not None:
                height = obj.getLiftHeight() if binding['name'] == 'lift' else obj.getDipHeight()
            configured = height is not None
            active = (
                configured
                and focus is not None
                and abs(focus - height) <= self.liftDipIndicatorTolerance
            )
            state = (configured, active)
            if state == binding['state']:
                continue
            binding['state'] = state
            painter = binding['painter']
            if painter is None:
                continue
            try:
                painter(configured, active)
            except Exception:
                binding['painter'] = None
                self.logger.exception(
                    f"{self.name()}: {binding['control']} failed to show the state of "
                    f"{binding['name']!r}; giving up on the indicator. The button still "
                    f"moves the objective."
                )

    def _liftDipPressed(self, control):
        """Move the objective to the height bound to *control*.

        Run on a worker thread with error reporting, exactly as a preset button is: an
        objective with no height stored for this action raises out of
        :meth:`moveLift`/:meth:`moveDip`, and that refusal has to reach the log and the
        error dialog rather than dying inside a Qt slot. The move itself goes through
        :meth:`setFocusDepth` and so through the motion planner, which checks the panic lock
        and takes the device reservations before anything turns.
        """
        binding = self._liftDipControls.get(control)
        if binding is None:
            return
        name = binding['name']
        asynch(
            self._runLiftDip,
            detach=True,
            raise_errors=f"Error moving {self.name()} to {name} height",
        )(name, binding['speed'])

    def _runLiftDip(self, name, speed):
        """Move to the *name* height and wait for the move, as one task.

        Waiting is what makes this a method rather than a direct ``asynch(self.moveLift)``:
        :meth:`moveLift` hands back a future instead of blocking, and a task whose body has
        returned stops the children it never awaited -- so the move would be stopped the
        instant it started. Waiting here also puts a failed *move* (a limit, a halted rig)
        inside the task that ``raise_errors`` is watching, not just a missing height.
        """
        mover = self.moveLift if name == 'lift' else self.moveDip
        mover(speed=speed).wait()

    def _releaseControls(self):
        """Release every control claimed by this device.

        Called from :meth:`quit`, and from :meth:`_setupControls` when a binding fails
        part-way. Covers the preset buttons too: acquisition is exclusive and strictly once
        until released, so a control this device still held after it went away could never
        be claimed again. Signals are disconnected wholesale -- nothing else is listening to
        a control this device owns.
        """
        for signal in (
            self.sigGlobalTransformChanged,
            self.sigObjectiveChanged,
            self.sigObjectiveHeightsChanged,
        ):
            try:
                signal.disconnect(self._liftDipStateChanged)
            except (TypeError, RuntimeError):
                pass
        controls = list(self._boundControls.values()) + list(self._presetControls)
        self._boundControls = {}
        self._liftDipControls = {}
        self._presetControls = {}
        for control in controls:
            for signal in (
                control.sigMoved,
                control.sigPressed,
                control.sigReleased,
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

    def positionDevice(self):
        if self._positionDevice is None:
            p = self
            while True:
                if p is None or isinstance(p, Stage) and p.capabilities()['setPos'][0] and p.capabilities()['setPos'][1]:
                    self._positionDevice = p
                    break
                p = p.parentDevice()
        return self._positionDevice


class Objective(Device, OptomechDevice):

    def __init__(self, config, scope, key):
        self._scope: Microscope = scope
        self._key = key
        name = config['name']

        Device.__init__(self, scope.dm, config, name)
        OptomechDevice.__init__(self, scope.dm, config, name)

        if 'offset' in config:
            self.setOffset(config['offset'])
        if 'scale' in config:
            self.setScale(config['scale'])

        heights = self.readConfigFile('heights')
        self._dipHeight = heights.get('dipHeight', None)
        self._liftHeight = heights.get('liftHeight', None)

    def getDipHeight(self):
        return self._dipHeight

    def setDipHeight(self, z):
        self._dipHeight = float(z)
        self._saveHeights()

    def getLiftHeight(self):
        return self._liftHeight

    def setLiftHeight(self, z):
        self._liftHeight = float(z)
        self._saveHeights()

    def _saveHeights(self):
        heights = {}
        if self._dipHeight is not None:
            heights['dipHeight'] = self._dipHeight
        if self._liftHeight is not None:
            heights['liftHeight'] = self._liftHeight
        self.writeConfigFile(heights, 'heights')
        # Lift/dip buttons show whether a height exists and whether focus is at it.
        self._scope.sigObjectiveHeightsChanged.emit(self)

    def getGeometry(self, name=None):
        return None

    def getGeometryForMicroscope(self, name):
        return super().getGeometry(name)

    def physicalTransform(self, subdev=None):
        tr = TTransform(offset=self.offset())
        dev = self.getSubdevice(subdev)
        if dev is None:
            return tr
        else:
            return tr * dev.physicalTransform()

    def setOffset(self, pos):
        tr = self.deviceTransform()
        if len(pos) < 3:
            pos = (pos[0], pos[1], 0)
        tr.offset = pos
        # TODO modify in place makes set redundant
        self.setDeviceTransform(tr)

    def setScale(self, scale):
        if not hasattr(scale, '__len__'):
            scale = (scale, scale, 1)
        if len(scale) < 3:
            scale = (scale[0], scale[1], 1)

        tr = self.deviceTransform()
        tr.scale = scale
        # TODO modify in place makes set redundant
        self.setDeviceTransform(tr)

    def offset(self):
        return self.deviceTransform().offset

    def scale(self):
        return self.deviceTransform().scale

    def key(self):
        return self._key

    def scope(self):
        return self._scope

    @property
    def radius(self):
        return self.config.get('radius')

    def __repr__(self):
        return (f"<Objective {self._scope.name()}.{self.name()} "
                f"offset={self.offset()[0]:0.2g},{self.offset()[1]:0.2g} "
                f"scale={self.scale()[0]:0.2g}>")


class ScopeGUI(Qt.QWidget):
    """Microscope GUI displayed in Manager window.
    Shows selection of objectives and allows scale/offset to be changed for each."""

    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigObjectiveChanged.connect(self.objectiveChanged)

        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev._allObjectives()
        self.switchN = len(self.objList)
        self.objWidgets = {}
        self.dipLiftButtons = {}  # {slot_key: (setDipBtn, goDipBtn, setLiftBtn, goLiftBtn)}
        self.blockSpinChange = False
        for row, obj in enumerate(self.objList, start=1):
            ## For each objective, create a set of widgets for selecting and updating.
            c = Qt.QComboBox()
            r = Qt.QRadioButton(obj)

            xs = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True, compactHeight=False)
            ys = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True, compactHeight=False)
            zs = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True, compactHeight=False)
            xyss = pg.SpinBox(step=1e-7, bounds=(1e-10, None), compactHeight=False)
            zss = pg.SpinBox(step=1e-7, bounds=(1e-10, None), compactHeight=False)

            xs.index = ys.index = zs.index = xyss.index = zss.index = obj  ## used to determine which row has changed
            widgets = (r, c, xs, ys, zs, xyss, zss)
            for col, w in enumerate(widgets):
                self.ui.objectiveLayout.addWidget(w, row * 2 - 1, col)
            self.objWidgets[obj] = widgets

            for o in self.objList[obj].values():
                c.addItem(o.name(), o)
                o.sigTransformChanged.connect(self.updateSpins)

            ## objectives are accessed like:
            ##   index = changedWidget.index
            ##   combo = self.objWidgets[index][1]
            ##   obj = combo.currentData()

            r.clicked.connect(self.objRadioClicked)
            c.currentIndexChanged.connect(self.objComboChanged)
            xs.sigValueChanged.connect(self.offsetSpinChanged)
            ys.sigValueChanged.connect(self.offsetSpinChanged)
            zs.sigValueChanged.connect(self.offsetSpinChanged)
            xyss.sigValueChanged.connect(self.scaleSpinChanged)
            zss.sigValueChanged.connect(self.scaleSpinChanged)

            # Dip / lift position buttons
            setDipBtn = Qt.QPushButton('Set Dip')
            goDipBtn = Qt.QPushButton('Dip!')
            setLiftBtn = Qt.QPushButton('Set Lift')
            goLiftBtn = Qt.QPushButton('Lift!')

            for col, btn in enumerate((setDipBtn, goDipBtn, setLiftBtn, goLiftBtn), start=2):
                self.ui.objectiveLayout.addWidget(btn, row * 2, col)
            self.dipLiftButtons[obj] = (setDipBtn, goDipBtn, setLiftBtn, goLiftBtn)

            # Use default-argument capture to bind obj at definition time
            setDipBtn.clicked.connect(lambda checked, o=obj: self._setDipHeight(o))
            goDipBtn.clicked.connect(lambda checked, o=obj: self._goDipHeight(o))
            setLiftBtn.clicked.connect(lambda checked, o=obj: self._setLiftHeight(o))
            goLiftBtn.clicked.connect(lambda checked, o=obj: self._goLiftHeight(o))

            self._updateDipLiftButtons(obj)

        # note: a preset's control-surface button is claimed by the device itself, so that
        # it works whether or not this window is open
        for preset in dev.presets:
            btn = Qt.QPushButton(preset)
            btn.setObjectName(preset)
            self.ui.presetLayout.addWidget(btn)
            btn.clicked.connect(self.loadPreset)
        self.updateSpins()

    def _currentObjectiveForSlot(self, slot):
        """Return the Objective currently selected in the combo for the given slot."""
        combo = self.objWidgets[slot][1]
        return combo.currentData()

    def _setDipHeight(self, slot):
        obj = self._currentObjectiveForSlot(slot)
        obj.setDipHeight(self.dev.getFocusDepth())
        self._updateDipLiftButtons(slot)

    def _goDipHeight(self, slot):
        obj = self._currentObjectiveForSlot(slot)
        z = obj.getDipHeight()
        if z is not None:
            self.dev.setFocusDepth(z, name=f"{self.dev.name()} go to dip height")

    def _setLiftHeight(self, slot):
        obj = self._currentObjectiveForSlot(slot)
        obj.setLiftHeight(self.dev.getFocusDepth())
        self._updateDipLiftButtons(slot)

    def _goLiftHeight(self, slot):
        obj = self._currentObjectiveForSlot(slot)
        z = obj.getLiftHeight()
        if z is not None:
            self.dev.setFocusDepth(z, name=f"{self.dev.name()} go to lift height")

    def _updateDipLiftButtons(self, slot):
        """Enable/disable Go buttons based on whether heights have been set."""
        obj = self._currentObjectiveForSlot(slot)
        (setDipBtn, goDipBtn, setLiftBtn, goLiftBtn) = self.dipLiftButtons[slot]
        goDipBtn.setEnabled(obj.getDipHeight() is not None)
        goLiftBtn.setEnabled(obj.getLiftHeight() is not None)

    def loadPreset(self):
        btn = self.sender()
        name = btn.objectName()
        asynch(self.dev.loadPreset, detach=True, raise_errors=f"Error loading preset {name}")(name)

    def objectiveChanged(self, obj):
        ## Microscope says new objective has been selected; update selection radio
        (obj, old) = obj
        index = obj.key()[0]
        self.objWidgets[index][0].setChecked(True)

    def objRadioClicked(self):
        for obj in self.objList:
            if self.objWidgets[obj][0].isChecked():
                self.dev.setObjectiveIndex(obj)
                break

    def objComboChanged(self):
        combo = self.sender()
        self.dev.selectObjective(combo.itemData(combo.currentIndex()))
        self.blockSpinChange = True
        try:
            self.updateSpins()
        finally:
            self.blockSpinChange = False
        # Refresh dip/lift button state for this slot
        for slot, widgets in self.objWidgets.items():
            if widgets[1] is combo:
                self._updateDipLiftButtons(slot)
                break

    def offsetSpinChanged(self, spin):
        if self.blockSpinChange:
            return
        index = spin.index
        (r, combo, xs, ys, zs, xyss, zss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        if callable(getattr(obj, "toPyObject", None)):
            obj = obj.toPyObject()
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setOffset((xs.value(), ys.value(), zs.value()))
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)

    def scaleSpinChanged(self, spin):
        if self.blockSpinChange:
            return
        index = spin.index
        (r, combo, xs, ys, zs, xyss, zss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        if callable(getattr(obj, "toPyObject", None)):
            obj = obj.toPyObject()
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setScale((xyss.value(), xyss.value(), zss.value()))
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)

    def updateSpins(self):
        for k, w in self.objWidgets.items():
            (r, combo, xs, ys, zs, xyss, zss) = w
            obj = combo.itemData(combo.currentIndex())
            if callable(getattr(obj, "toPyObject", None)):
                obj = obj.toPyObject()

            offset = obj.offset()
            xs.setValue(offset[0])
            ys.setValue(offset[1])
            zs.setValue(offset[2])

            scale = obj.scale()
            xyss.setValue(scale[0])
            zss.setValue(scale[2])


class ScopeCameraModInterface(CameraModuleInterface):
    """Implements focus control user interface for use in the camera module.
    """
    canImage = False

    def __init__(self, dev, win):
        CameraModuleInterface.__init__(self, dev, win)

        self.ctrl = Qt.QWidget()
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.ctrl.setLayout(self.layout)

        self.plot = win.getDepthView()

        # Create Z-position widget
        self.zPositionWidget = ZPositionWidget(self.plot, movable=True)
        self.zPositionWidget.sigTargetChangeRequested.connect(self.focusChangedFromWidget)

        # Ideally, the sample orientation, height, and anatomical identity would be contained
        # in a Sample or Slice object elsewhere...

        # Add controls

        self.setSurfaceBtn = Qt.QPushButton('Set Surface')
        self.setSurfaceBtn.clicked.connect(self.setSurfaceClicked)
        self.layout.addWidget(self.setSurfaceBtn, 0, 0)  # Add to our layout

        self.findSurfaceBtn = FutureButton(
            self.findSurface, 'Find Surface', stoppable=True, processing='Scanning...', failure='Failed!')
        self.layout.addWidget(self.findSurfaceBtn, 1, 0)

        # Get depth label from the widget and add it to our layout
        self.layout.addWidget(self.zPositionWidget.depthLabel, 2, 0)

        # add a spacer
        self.layout.setRowStretch(3, 1)

        # Connect device signals
        dev.sigGlobalTransformChanged.connect(self.transformChanged)
        dev.sigSurfaceDepthChanged.connect(self.surfaceDepthChanged)
        self._focusDev = dev.focusDevice()
        if self._focusDev is not None:
            self._focusDev.sigTargetChanged.connect(self.targetChanged)

        # Initialize with current values
        sd = dev.getSurfaceDepth()
        if sd is not None:
            self.zPositionWidget.setSurfaceDepth(sd)

        self.transformChanged()

    def setSurfaceClicked(self):
        focus = self.getDevice().getFocusDepth()
        self.getDevice().setSurfaceDepth(focus)
        self.transformChanged()

    def findSurface(self):
        return asynch_with_qt_signals(self.getDevice().findSurfaceDepth)(self.getDevice().getDefaultImager())

    def surfaceDepthChanged(self, depth):
        self.zPositionWidget.setSurfaceDepth(depth)

    def transformChanged(self):
        self.zPositionWidget.setFocusDepth(self.getDevice().getFocusDepth())
        self.updateTargetDepth()

    def targetChanged(self, dev, target):
        self.updateTargetDepth()

    def updateTargetDepth(self):
        """Show the focus device's commanded target as a focal plane depth.

        Applied as a displacement from the device's current position, since the
        objective may carry an offset and scale relative to the focus device.
        """
        fd = self.getDevice().focusDevice()
        if fd is None:
            return
        focus = self.getDevice().getFocusDepth()
        dif = fd.globalTargetPosition()[2] - fd.globalPosition()[2]
        self.zPositionWidget.setTargetDepth(focus + dif)

    def focusChangedFromWidget(self, depth):
        """Request a focus depth the user dragged the target line to.

        Every path that does not reach the device restores the line to the device's
        own target.
        """
        try:
            mfut = self.getDevice().setFocusDepth(
                depth, name=f"{self.getDevice().name()} focus from Z-widget"
            )
        except GlobalHaltException:
            self.updateTargetDepth()
            return  # not re-raised; the panic dialog already explains the refusal
        except Exception:
            self.updateTargetDepth()
            raise
        mfut.sigFinished.connect(self._handleRefocusFinished)
        if mfut.is_done:
            # A refused move arrives already finished, so sigFinished fired before the
            # connection above existed.
            self._handleRefocusFinished()

    def _handleRefocusFinished(self, *args):
        self.updateTargetDepth()

    def controlWidget(self):
        return self.ctrl

    def boundingRect(self):
        return None

    def quit(self):
        if self._focusDev is not None:
            pg.disconnect(self._focusDev.sigTargetChanged, self.targetChanged)
            self._focusDev = None
