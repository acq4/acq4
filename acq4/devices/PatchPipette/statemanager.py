from __future__ import print_function
from collections import OrderedDict
try:
    import queue
except ImportError:
    import Queue as queue
from acq4.util import Qt
from acq4.pyqtgraph import disconnect
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
    stateHandlers = OrderedDict([
        ('out', states.PatchPipetteOutState),
        ('clean', states.PatchPipetteCleanState),
        ('bath', states.PatchPipetteBathState),
        ('approach', states.PatchPipetteApproachState),
        ('cell detect', states.PatchPipetteCellDetectState),
        ('seal', states.PatchPipetteSealState),
        ('cell attached', states.PatchPipetteCellAttachedState),
        ('break in', states.PatchPipetteBreakInState),
        ('whole cell', states.PatchPipetteWholeCellState),
        ('broken', states.PatchPipetteBrokenState),
        ('fouled', states.PatchPipetteFouledState),
    ])

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
            ret = returnQueue.get(timeout=10)
        except queue.Empty:
            raise Exception("State change request timed out.")
        if isinstance(ret, Exception):
            raise ret
        else:
            return ret

    def _stateChangeRequested(self, state, returnQueue):
        try:
            if state not in self.stateHandlers:
                raise Exception("Unknown patch pipette state %r" % state)
            ret = self.configureState(state)
        except Exception as exc:
            ret = exc
        returnQueue.put(ret)

    def configureState(self, state, *args, **kwds):
        self.stopJob()
        stateHandler = self.stateHandlers[state]

        # assemble state config from defaults and anything specified in args here
        config = self.stateConfig.get(state, {}).copy()
        config.update(kwds.pop('config', {}))
        kwds['config'] = config

        job = stateHandler(self.dev, *args, **kwds)
        self.currentJob = job
        job.sigStateChanged.connect(self.jobStateChanged)
        job.sigFinished.connect(self.jobFinished)
        self.dev._setState(state)
        job.initialize()
        self.sigStateChanged.emit(self, job)
        return job

    def activeChanged(self, pip, active):
        if active:
            self.configureState(self.dev.state)
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
            disconnect(job.sigStateChanged, self.jobStateChanged)
            disconnect(job.sigFinished, self.jobFinished)

    def jobStateChanged(self, job, state):
        self.dev.logEvent("stateManagerEvent", info=state)

    def jobFinished(self, job):
        disconnect(job.sigStateChanged, self.jobStateChanged)
        disconnect(job.sigFinished, self.jobFinished)
        if job.nextState is not None:
            self.requestStateChange(job.nextState)
