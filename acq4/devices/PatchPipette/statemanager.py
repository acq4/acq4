from __future__ import print_function

import sys
from collections import OrderedDict

from six.moves import queue

from acq4.util import Qt
from pyqtgraph import disconnect
from acq4.util.debug import printExc
from . import states


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
                states.PatchPipetteOutState,
                states.PatchPipetteBathState,
                states.PatchPipetteApproachState,
                states.PatchPipetteCellDetectState,
                states.PatchPipetteSealState,
                states.PatchPipetteCellAttachedState,
                states.PatchPipetteBreakInState,
                states.PatchPipetteWholeCellState,
                states.PatchPipetteResealState,
                states.PatchPipetteBlowoutState,
                states.PatchPipetteBrokenState,
                states.PatchPipetteFouledState,
                states.PatchPipetteCleanState,
            ]
        ]
    )

    sigStateChanged = Qt.Signal(object, object)  # self, PatchPipetteState
    _sigStateChangeRequested = Qt.Signal(object, object)  # state, return queue

    def __init__(self, dev):
        Qt.QObject.__init__(self)
        self.dev = dev
        self.dev.sigStateChanged.connect(self.stateChanged)
        self.dev.sigActiveChanged.connect(self.activeChanged)
        self.currentJob = None

        # default state configuration parameters
        self.stateConfig = {}  # {state: {config options}}

        self._sigStateChangeRequested.connect(self._stateChangeRequested)

    def getState(self):
        """Return the currently active state.
        """
        return self.currentJob

    def listStates(self):
        return list(self.stateHandlers.keys())

    def setStateConfig(self, config):
        """Set configuration options to be used when initializing states.

        Must be a dict like {'statename': {'opt': value}, ...}.
        """
        self.stateConfig = config

    def stateChanged(self, oldState, newState):
        """Called when state has changed (possibly by user)
        """
        pass

    def requestStateChange(self, state):
        """Pipette has requested a state change; either accept and configure the new
        state or reject the new state.

        Return the name of the state that has been chosen.
        """
        # state changes involve the construction of numerous QObjects with signal/slot connections;
        # the indivudual state classes assume that they are owned by a thread with an event loop.
        # SO: we need to process state transitions in the main thread. If this method is called
        # from the main thread, then the emit() below will be processed immediately. Otherwise,
        # we wait until the main thread processes the signal and sends back the result.
        returnQueue = queue.Queue()
        self._sigStateChangeRequested.emit(state, returnQueue)
        try:
            success, ret = returnQueue.get(timeout=10)
        except queue.Empty:
            raise Exception("State change request timed out.")

        if success:
            return ret
        else:
            sys.excepthook(*ret)
            raise RuntimeError("Error requesting state change to %r; original exception appears above." % state)

    def _stateChangeRequested(self, state, returnQueue):
        try:
            if state not in self.stateHandlers:
                raise Exception("Unknown patch pipette state %r" % state)
            ret = (True, self.configureState(state))
        except Exception as exc:
            ret = (False, sys.exc_info())
        returnQueue.put(ret)

    def configureState(self, state, *args, **kwds):
        oldJob = self.currentJob
        allowReset = kwds.pop('_allowReset', True)
        self.stopJob()
        try:
            stateHandler = self.stateHandlers[state]

            # assemble state config from defaults and anything specified in args here
            config = self.stateConfig.get(state, {}).copy()
            config.update(kwds.pop('config', {}))
            kwds['config'] = config

            job = stateHandler(self.dev, *args, **kwds)
            job.sigStateChanged.connect(self.jobStateChanged)
            job.sigFinished.connect(self.jobFinished)
            oldState = None if oldJob is None else oldJob.stateName
            self.currentJob = job
            self.dev._setState(state, oldState)
            job.initialize()
            self.sigStateChanged.emit(self, job)
            return job
        except Exception:
            # in case of failure, attempt to restore previous state
            self.currentJob = None
            if not allowReset or oldJob is None:
                raise
            try:
                self.configureState(oldJob.stateName, _allowReset=False)
            except Exception:
                printExc("Error occurred while trying to reset state from a previous error:")
            raise

    def activeChanged(self, pip, active):
        if active:
            self.configureState(self.getState().stateName)
        else:
            self.stopJob()
            self.dev.enableTestPulse(False)
            self.dev.pressureDevice.setPressure(source='atmosphere')

    def quit(self):
        disconnect(self.dev.sigStateChanged, self.stateChanged)
        disconnect(self.dev.sigActiveChanged, self.activeChanged)
        self.stopJob()

    ## Background job handling

    def stopJob(self):
        job = self.currentJob
        if job is not None:
            job.stop()
            try:
                job.wait(timeout=10)
            except job.Timeout:
                printExc("Timed out waiting for job %s to complete" % job)
            except Exception:
                # hopefully someone else is watching this future for errors!
                pass

    def jobStateChanged(self, job, state):
        self.dev.emitNewEvent("state_event", {'state': job.stateName, 'info': state})

    def jobFinished(self, job):
        try:
            job.cleanup()
        except Exception:
            printExc("Error during %s cleanup:" % job.stateName)
        disconnect(job.sigStateChanged, self.jobStateChanged)
        disconnect(job.sigFinished, self.jobFinished)
        if job.nextState is not None:
            self.requestStateChange(job.nextState)
