from __future__ import print_function
from collections import OrderedDict
from acq4.util.Qt import QtCore
from acq4.pyqtgraph import disconnect
from acq4.util.debug import printExc
from . import states


class PatchPipetteStateManager(QtCore.QObject):
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

    sigStateChanged = QtCore.Signal(object, object)  # self, PatchPipetteState

    def __init__(self, dev):
        QtCore.QObject.__init__(self)
        self.dev = dev
        self.dev.sigStateChanged.connect(self.stateChanged)
        self.dev.sigActiveChanged.connect(self.activeChanged)
        self.currentJob = None

    def listStates(self):
        return list(self.stateHandlers.keys())

    def stateChanged(self, oldState, newState):
        """Called when state has changed (possibly by user)
        """
        pass

    def requestStateChange(self, state):
        """Pipette has requested a state change; either accept and configure the new
        state or reject the new state.

        Return the name of the state that has been chosen.
        """
        if state not in self.stateHandlers:
            raise Exception("Unknown patch pipette state %r" % state)
        return self.configureState(state)

    def configureState(self, state, *args, **kwds):
        self.stopJob()
        stateHandler = self.stateHandlers[state]
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
            self.dev.pressureDevice.setSource('atmosphere')

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
