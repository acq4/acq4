import contextlib
import functools
import inspect
from collections import OrderedDict
from typing import Optional

from docstring_parser import parse

from acq4 import getManager
from acq4.logging_config import get_logger
from acq4.util import Qt
from acq4.util.task import Stopped, throughline
from pyqtgraph import disconnect
from pyqtgraph.parametertree import Parameter
from . import states

logger = get_logger(__name__)


@contextlib.contextmanager
def stateJobContext():
    """Build a state job as a top-level operation, outside any current throughline.

    A state transition creates the next state's job from within the outgoing state's
    finish handling, and a task captures its context at construction. Without this,
    each state's throughline nests inside its predecessor's and the chain grows by one
    name per transition, forever. States are siblings, not children -- the same reason
    their jobs are created with detach=True.
    """
    with throughline.restore(()):
        yield


class PatchPipetteStateManager(Qt.QObject):
    """Used to handle state transitions and to spawn background threads for pipette automation

    State manager affects:
     - pipette state ('bath', 'seal', 'whole cell', etc.)
     - clamp mode
     - clamp holding value
     - pressure
     - test pulse
     - pipette position

    Note: all the real work is done in the individual state classes (see acq4.devices.PatchPipette.states)
    """

    stateHandlers = OrderedDict(
        [
            (state.stateName, state)
            for state in [
                states.OutState,
                states.BathState,
                states.ApproachState,
                states.CellDetectState,
                states.SealState,
                states.ContactCellState,
                states.CellAttachedState,
                states.BreakInState,
                states.WholeCellState,
                states.ClearAccessState,
                states.ResealState,
                states.OutsideOutState,
                states.BlowoutState,
                states.BrokenState,
                states.FouledState,
                states.CleanState,
                states.NucleusCollectState,
                states.MoveNucleusToHomeState,
                states.RefillState,
            ]
        ]
    )

    sigStateChanged = Qt.Signal(object, object)  # self, PatchPipetteState
    sigProfileChanged = Qt.Signal(object, object)  # self, profile_name

    profiles: dict[str: dict[str: dict[str: object]]] = {}  # {profile_name: {state_name: {config_options}}}
    _profilesLoadedFromConfig = False

    def __init__(self, dev):
        Qt.QObject.__init__(self)
        self.dev = dev
        self.logger = get_logger(f"{dev.name()}.StateManager")
        self.dev.sigStateChanged.connect(self.stateChanged)
        self.dev.sigActiveChanged.connect(self.activeChanged)
        self.currentJob = None
        self._profile = None
        # The job whose abort callback is currently registered with the Panic Lock,
        # or None. This manager is a *transient* participant ("Panic Lock Spec.md"
        # §10.1): it holds a registration only while a state job is running. Keeping
        # the owning job here -- rather than a bare bool -- is what makes
        # unregistration safe to attempt from several places at once; see
        # _unregisterHaltCallback().
        self._haltRegisteredJob = None

        if 'default' in self.listProfiles():
            self.setProfile('default')

    @classmethod
    def listProfiles(cls):
        cls._loadGlobalProfilesOnce()
        return list(cls.profiles.keys())

    @classmethod
    def listStates(cls):
        return list(cls.stateHandlers.keys())

    @classmethod
    def getStateClass(cls, name) -> states.PatchPipetteState:
        return cls.stateHandlers[name]

    @classmethod
    def getProfileConfig(cls, name):
        cls._loadGlobalProfilesOnce()
        if name not in cls.profiles:
            raise KeyError(f"Unknown patch profile {name}")
        return cls.profiles[name]

    @staticmethod
    def buildPatchProfilesParameters():
        params = []
        for profile in PatchPipetteStateManager.listProfiles():
            params.append(ProfileParameter(profile))
            Qt.QApplication.processEvents()
        return Parameter.create(name='profiles', type='group', value=None, children=params)

    @staticmethod
    def _loadGlobalProfilesOnce():
        if PatchPipetteStateManager._profilesLoadedFromConfig:
            return
        PatchPipetteStateManager._profilesLoadedFromConfig = True
        man = getManager()
        for k, v in man.config.get('misc', {}).get('patchProfiles', {}).items():
            v = v.copy()
            PatchPipetteStateManager.addProfile(name=k, config=v)

    @classmethod
    def addProfile(cls, name: str, config: dict, overwrite=False):
        if name in cls.profiles and not overwrite:
            raise ValueError(f"Patch profile {name} already exists")
        mistakes = []
        for state, state_config in config.items():
            if state == 'copyFrom':
                if not isinstance(state_config, str):
                    mistakes.append(f"Invalid copyFrom value {state_config!r} in profile {name}")
                if state_config and state_config not in cls.profiles:
                    mistakes.append(f"Unknown profile {state_config!r} to copy from in profile {name}")
                continue
            if state not in cls.stateHandlers:
                mistakes.append(f"Unknown patch state {state!r} in profile {name}")
                continue
            if not isinstance(state_config, dict):
                mistakes.append(f"Invalid configuration for state {state!r} in profile {name}")
                continue
            for param, value in state_config.items():
                if not isinstance(param, str):
                    mistakes.append(f"Invalid parameter name {param!r} in state {state!r} of profile {name}")
                    continue
                if param not in cls.getStateClass(state).defaultConfig():
                    mistakes.append(f"Unknown parameter {param!r} in state {state!r} of profile {name}")
        if mistakes:
            raise ValueError(f"Errors in profile {name}:\n" + "\n".join(mistakes))
        cls.profiles[name] = config

    @classmethod
    def getStateConfig(cls, state: str, profile: Optional[str]):
        """
        Return the configuration options for the given state and profile, or just the defaults if no profile is
        specified.
        """
        if profile is None:
            config = {}
        else:
            config = cls.getProfileConfig(profile)
        if copy_from := config.get('copyFrom', None):
            defaults = cls.getStateConfig(state, copy_from)
        else:
            defaults = cls.getStateClass(state).defaultConfig()
        config = config.get(state, {})
        return {
            param: config.get(param, defaults.get(param, None))
            for param in set(list(defaults.keys()) + list(config.keys()))
        }

    def abort(self):
        """Stop the running state job; the Panic Lock abort callback (§5.2).

        Registered only while a job is running (§10.1). ``allowNextState=False`` is
        the load-bearing argument: stopping a state normally hands off to its
        ``nextState``, and a halt must not start anything new.

        §6.1 lists "Stopping the running state job" as Allowed while HALTED, so this
        callback cannot trip its own guard (§6.3). It can still surface an error out
        of a state's own ``_cleanup()`` handler -- see §12 item 6 -- but ``stopJob()``
        already logs and absorbs those rather than letting them escape.
        """
        self.stopJob(allowNextState=False)

    def _registerHaltCallback(self, job):
        """Take a Panic Lock registration on behalf of *job* (§10.1).

        Called before ``job.start()``, not after: a halt landing in the middle of
        ``start()`` must still find a callback to run.
        """
        self._haltRegisteredJob = job
        self.dev.dm.globalHalt.add_abort_callback(
            self.abort, name=f"{self.dev.name()}.stateManager.abort")

    def _unregisterHaltCallback(self, job):
        """Drop the registration, but only if *job* still owns it (§10.1).

        Every caller passes the job it believes is finishing. Because the registered
        callable is this manager's single bound ``abort`` -- one registration, not one
        per job -- a late unregistration from a job that has already been succeeded by
        another would otherwise silently disarm the *new* job. The identity check makes
        every unregistration path safe to call unconditionally and in any order, which
        is what lets several of them exist at once.
        """
        if self._haltRegisteredJob is not job:
            return
        self._haltRegisteredJob = None
        self.dev.dm.globalHalt.remove_abort_callback(self.abort)

    def _jobFinishCallback(self, job, result, exc):
        """Last-resort unregistration, run by the job's own finish callbacks.

        §10.1 requires unregistration on *every* exit path, including death by an
        unhandled ``GlobalHaltException``, and warns that these jobs cannot all be
        wrapped in one ``try:/finally:``. ``jobFinished()`` is the normal path and
        covers a job that returns, stops, or raises -- but it is reached through
        ``sigFinished``, which ``QtFriendlyTask._on_task_finished`` only emits *after*
        calling the state's ``on_finish`` hook; if that hook itself raises, gentletask
        logs it and the signal is never emitted. This callback is registered directly
        on the job, so it runs from ``_run_callbacks()`` regardless.

        It is ordered *after* the signal-emitting callback (that one is added in
        ``QtFriendlyTask.__init__``, before this class can add anything), so by the
        time it runs a transition to the next state may already have re-registered.
        ``_unregisterHaltCallback`` is what makes that harmless.
        """
        self._unregisterHaltCallback(job)

    def setProfile(self, profile: str):
        """Set the current patch profile."""
        self._profile = profile
        self.logger.debug(f"Profile set to {profile}")
        self.sigProfileChanged.emit(self, profile)

    def getState(self):
        """Return the currently active state.
        """
        return self.currentJob

    def stateChanged(self, oldState, newState):
        """Called when state has changed (possibly by user)
        """
        pass

    def requestStateChange(self, state, **config):
        """Pipette has requested a state change; either accept and configure the new
        state or reject the new state.

        Return the state that has been chosen.
        """
        if state not in self.stateHandlers:
            raise ValueError(f"Unknown patch pipette state {state!r}")
        return self.configureState(state, configOverride=config)

    def configureState(self, state, allowReset=True, configOverride=None):
        with throughline(name=f"{self.dev.name()} -> state {state!r}"):
            return self._configureState(state, allowReset=allowReset, configOverride=configOverride)

    # States that may still be started while the rig is HALTED. §6.1 refuses
    # "starting a new state other than `out`"; §10.1 is the reason for the
    # exception -- "states fail to `out`" -- so a job dying of its own
    # GlobalHaltException must still be able to land there. OutState only vents to
    # atmosphere, sets VC holding to 0 and disables the test pulse: no motion, no
    # energy, and every one of those is on the Allowed side of its device's guard.
    _statesAllowedWhileHalted = ('out',)

    def _configureState(self, state, allowReset=True, configOverride=None):
        # Panic Lock guard (§6.1/§10.1). First statement in the funnel that both
        # requestStateChange() and configureState() go through, and deliberately
        # ahead of every side effect: no job object is built, the running job is not
        # stopped, and the fallback cascade below is never entered, so a refused
        # transition leaves the manager exactly as it found it.
        #
        # This raises rather than refusing quietly, for three reasons. §6.1 says
        # Raise. The return value of requestStateChange()/configureState() is the
        # job that was started, and there is no value that honestly means "no state
        # was started" -- returning the *old* job would tell the caller a transition
        # happened, and returning None would be dereferenced by callers that expect
        # a job. And an unhandled GlobalHaltException is exactly how a state job is
        # meant to die (§10.1): swallowing it here would let an automation loop
        # believe its request was merely declined and try the next state, which is
        # the retry-spin §12 item 1 warns about, with the added twist that nothing
        # would appear in the log.
        if state not in self._statesAllowedWhileHalted:
            self.dev.dm.globalHalt.check()
        oldJob = self.currentJob
        fallback = None
        if oldJob is not None:
            fallback = {"state": oldJob.stateName, **oldJob.config}
        try:
            stateHandler = self.stateHandlers[state]

            # assemble state config from defaults and anything specified in args here
            config = self.getStateConfig(state, self._profile)
            if configOverride is not None:
                config.update(configOverride)

            self.logger.debug(f"Configuring next state {state} with config: {config}")
            with stateJobContext():
                job = stateHandler(self.dev, config)
        except Exception:
            raise
        else:
            self.logger.debug(f"Stopping previous state {oldJob.stateName if oldJob else None}")
            self.stopJob(allowNextState=False)

        try:
            fallback = job.nextState
            job.sigStateChanged.connect(self.jobStateChanged, Qt.Qt.DirectConnection)  # no gui
            job.sigFinished.connect(self.jobFinished, Qt.Qt.DirectConnection)  # no gui
            oldState = None if oldJob is None else oldJob.stateName
            self.currentJob = job
            self.dev._setState(state, oldState)  # logging / accounting
            self._registerHaltCallback(job)
            job.add_finish_callback(functools.partial(self._jobFinishCallback, job))
            job.start()
            self.sigStateChanged.emit(self, job)
            return job
        except Exception:
            # in case of failure, go to fallback state.
            # Log the *primary* exception here. Without this, an error thrown while starting
            # `state` (e.g. in job.start() or a sigStateChanged slot, both of which run
            # synchronously in this thread) is silently swallowed: the state is entered
            # (_setState already emitted its state_change) and then immediately bounced to its
            # fallbackState with no explanation, because the re-raise below unwinds into a Qt
            # DirectConnection signal handler that discards it.
            self.currentJob = None
            # There is no job to abort any more, and the fallback below will take its
            # own registration if it starts (§10.1).
            self._unregisterHaltCallback(job)
            fallbackState = fallback["state"] if fallback else None
            self.logger.exception(
                f"Error while starting state {state!r}; falling back to {fallbackState!r}"
            )
            if not allowReset or fallback is None:
                raise
            try:
                self.configureState(fallback["state"], allowReset=False, configOverride=fallback)
            except Exception:
                self.logger.exception("Error occurred while trying to reset state from a previous error:")
            raise

    def activeChanged(self, pip, active):
        if active and self.getState() is not None:
            self.configureState(self.getState().stateName, configOverride=self.getState().config)
        else:
            self.stopJob()
            if self.dev.clampDevice is not None:
                self.dev.clampDevice.enableTestPulse(False)
            if self.dev.pressureDevice is not None:
                self.dev.pressureDevice.setPressure(source='atmosphere')

    def quit(self):
        disconnect(self.dev.sigStateChanged, self.stateChanged)
        disconnect(self.dev.sigActiveChanged, self.activeChanged)
        self.stopJob(allowNextState=False)
        # Belt and braces: stopJob() does nothing when no job is running, but a
        # registration must never outlive the manager that owns it (§10.1).
        self._unregisterHaltCallback(self._haltRegisteredJob)

    def stopJob(self, allowNextState=True):
        job = self.currentJob
        if job is not None:
            self.logger.debug(f"Stopping job {job.stateName}; allowNextState={allowNextState}")
            # disconnect; we'll call jobFinished directly
            disconnect(job.sigFinished, self.jobFinished)
            job.stop()
            try:
                job.wait(timeout=10)
            except job.Timeout:
                self.logger.warning(f"Timed out waiting for job {job} to complete")
            except Stopped:
                pass
            except Exception:
                self.logger.warning(f"{self.dev.name()} failed in state {job.stateName}", exc_info=True)
            self.jobFinished(job, allowNextState=allowNextState)

    def jobStateChanged(self, job, state):
        self.dev.emitNewEvent("state_event", {'state': job.stateName, 'info': state})

    def jobFinished(self, job, allowNextState=True):
        self.logger.debug(f"Job {job.stateName} finished; allowNextState={allowNextState}")
        # First thing, and before any transition to the next state: this job is over,
        # so its Panic Lock registration must go (§10.1). Doing it here rather than at
        # the end covers the cleanup and next-state code below raising, and keeps the
        # ordering right when requestStateChange() registers the successor.
        self._unregisterHaltCallback(job)
        try:
            job.cleanup().wait()
        except Stopped:
            self.logger.debug(f"{job.stateName} cleanup was stopped")
        except Exception:
            self.logger.exception(f"Error during {job.stateName} cleanup:")
        disconnect(job.sigStateChanged, self.jobStateChanged)
        disconnect(job.sigFinished, self.jobFinished)
        if allowNextState:
            if job.nextState.get("state") is not None:
                config = job.nextState
                state = config.pop("state")
                # Distinguish a deliberate transition (run() returned this state) from an
                # unexplained fallback: if the job was stopped/failed before run() returned, it
                # never chose a next state and we are using its default fallbackState. That case
                # otherwise looks like the state was "entered and immediately left" with no reason.
                if getattr(job, "_runChoseNextState", True):
                    self.logger.debug(f"{job.stateName} finished; transitioning to next state {state!r}")
                else:
                    self.logger.info(
                        f"{job.stateName} did not complete (stopped or failed before choosing a next "
                        f"state); using its default fallback next state {state!r}"
                    )
                self.requestStateChange(state, **config)
            else:
                self.logger.debug(f"No next state specified by {job.stateName}")


class ProfileParameter(Parameter):
    def __init__(self, profile):
        super().__init__(name=profile, type='group', value=None, children=[
            {'name': 'copyFrom', 'type': 'str', 'default': ''},
        ])
        config = PatchPipetteStateManager.getProfileConfig(profile)
        if 'copyFrom' in config:
            self['copyFrom'] = config['copyFrom']
        for state in PatchPipetteStateManager.listStates():
            self.addChild(StateParameter(state, profile))

    def reinitialize(self):
        for child in self:
            if isinstance(child, StateParameter):
                child.reinitialize()

    def applyDefaults(self, defaults):
        for key, val in defaults.items():
            self.child(key).applyDefaults(val)


class StateParameter(Parameter):
    # Class-level cache to avoid re-parsing docstrings
    _tooltip_cache = {}
    _base_tooltips = None  # Cache base tooltips separately since they're reused

    @staticmethod
    def _getTooltipsFromClass(cls):
        """Extract tooltips from a class's docstring."""
        try:
            docstring = inspect.getdoc(cls)
            if not docstring:
                return {}
            return {p.arg_name: p.description for p in parse(docstring).params}
        except Exception:
            logger.warning(f"Error parsing docstring for tooltips in class {cls.__name__}", exc_info=True)
            return {}

    @classmethod
    def _getBaseTooltips(cls):
        """Get base tooltips from PatchPipetteState, cached."""
        if cls._base_tooltips is None:
            cls._base_tooltips = cls._getTooltipsFromClass(states.PatchPipetteState)
        return cls._base_tooltips

    @classmethod
    def _getStateTooltips(cls, state_name):
        """Get tooltips for a state class, with caching and inheritance."""
        if state_name in cls._tooltip_cache:
            return cls._tooltip_cache[state_name]

        # Start with base parameters
        tooltips = cls._getBaseTooltips().copy()

        # Add/override with state-specific parameters
        state_params = cls._getTooltipsFromClass(PatchPipetteStateManager.getStateClass(state_name))
        tooltips.update(state_params)

        cls._tooltip_cache[state_name] = tooltips
        return tooltips

    def __init__(self, name, profile):
        super().__init__(name=name, type='group', value=None, children=[])
        self._profile = profile
        self._state = name
        tooltips = self._getStateTooltips(name)
        profile_config = PatchPipetteStateManager.getProfileConfig(profile)
        if profile_config.get('copyFrom', None):
            defaults = PatchPipetteStateManager.getStateConfig(name, profile_config['copyFrom'])
        else:
            defaults = {}
        stateClass = PatchPipetteStateManager.getStateClass(name)
        config = PatchPipetteStateManager.getStateConfig(name, profile)
        for param_config in stateClass.parameterTreeConfig():
            param_name = param_config['name']
            if param_name in defaults:
                param_config['default'] = defaults[param_name]
            param_config['pinValueToDefault'] = True
            param_config.setdefault('value', None)
            if param_config['type'] == 'float' and param_config.get('suffix') is not None:
                param_config.setdefault('siPrefix', True)
            if param_name not in tooltips:
                logger.warning(f"No tooltip found for parameter '{param_name}' in state '{name}'")
            param = Parameter.create(**param_config, tooltip=tooltips.get(param_name))
            if config.get(param_name) is not None:
                param.setValue(config[param_name])
            self.addChild(param)

    def reinitialize(self):
        profile = self._profile
        name = self._state
        profile_config = PatchPipetteStateManager.getProfileConfig(profile)
        if profile_config.get('copyFrom', None):
            defaults = PatchPipetteStateManager.getStateConfig(name, profile_config['copyFrom'])
        else:
            defaults = PatchPipetteStateManager.getStateConfig(name, None)
        self.applyDefaults(defaults)

    def applyDefaults(self, defaults):
        for key, val in defaults.items():
            self.child(key).setDefault(val, updatePristineValues=True)
