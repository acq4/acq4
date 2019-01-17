from __future__ import print_function
from .states import (
    PatchPipetteBathFuture, 
    PatchPipetteCleanFuture, 
    PatchPipetteCellDetectFuture, 
    PatchPipetteSealFuture, 
)
from acq4.pyqtgraph import disconnect
from acq4.util.debug import printExc


class PatchPipetteStateManager(object):
    """Used to handle state transitions and to spawn background threads for pipette automation

    State manager affects:
     - pipette state ('bath', 'seal', 'whole cell', etc.)
     - clamp mode
     - clamp holding value
     - pressure
     - test pulse
     - pipette position
    """
    allowedStates = ['out', 'clean', 'bath', 'approach', 'cell detect', 'seal', 'attached', 'break in', 'whole cell', 'broken', 'fouled']

    jobTypes = {
        'bath': PatchPipetteBathFuture,
        'clean': PatchPipetteCleanFuture,
        'cell detect': PatchPipetteCellDetectFuture,
        'seal': PatchPipetteSealFuture,
    }

    def __init__(self, dev):
        self.pressureStates = {
            'out': 'atmosphere',
            'bath': 3500.,  # 0.5 PSI
            'seal': 'user',
        }
        self.clampStates = {   # mode, holding, TP
            'out': ('vc', 0, False),
            'bath': ('vc', 0, True),
            'cell detect': ('vc', 0, True),
            'on cell': ('vc', 0, True),
            'seal': ('vc', 0, True),
            'cell attached': ('vc', -70e-3, True),
            'break in': ('vc', -70e-3, True),
            'whole cell': ('vc', -70e-3, True),
        }

        self.dev = dev
        self.dev.sigTestPulseFinished.connect(self.testPulseFinished)
        self.dev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.dev.sigStateChanged.connect(self.stateChanged)
        self.dev.sigActiveChanged.connect(self.activeChanged)

        self.currentJob = None

    def testPulseFinished(self, dev, result):
        """Called when a test pulse is finished
        """
        pass

    def transformChanged(self):
        """Called when pipette moves relative to global coordinate system
        """
        pass

    def listStates(self):
        return self.allowedStates[:]

    def stateChanged(self, oldState, newState):
        """Called when state has changed (possibly by user)
        """
        pass

    def requestStateChange(self, state):
        """Pipette has requested a state change; either accept and configure the new
        state or reject the new state.

        Return the name of the state that has been chosen.
        """
        if state not in self.allowedStates:
            raise Exception("Unknown patch pipette state %r" % state)
        self.configureState(state)
        return state

    def configureState(self, state):
        if state == 'out':
            # assume that pipette has been changed
            self.dev.newPipette()

        self.setupPressureForState(state)
        self.setupClampForState(state)
        self.dev._setState(state)
        if state in self.jobTypes:
            self.startJob(state)

    def setupPressureForState(self, state):
        """Configure pressure for the requested state.
        """
        if not self.dev.active:
            return

        pdev = self.dev.pressureDevice
        if pdev is None:
            return
        pressure = self.pressureStates.get(state, None)
        if pressure is None:
            return
        
        if isinstance(pressure, str):
            pdev.setSource(pressure)
            pdev.setPressure(0)
        else:
            pdev.setPressure(pressure)
            pdev.setSource('regulator')

    def setupClampForState(self, state):
        if not self.dev.active:
            return

        cdev = self.dev.clampDevice
        mode, holding, tp = self.clampStates.get(state, (None, None, None))

        if mode is not None:
            cdev.setMode(mode)
            if holding is not None:
                cdev.setHolding(value=holding)

        if state == 'approach':
            cdev.autoPipetteOffset()
            self.dev.resetTestPulseHistory()
        
        if tp is not None:
            self.dev.enableTestPulse(tp)

    def activeChanged(self, pip, active):
        if active:
            self.configureState(self.dev.state)
        else:
            self.dev.enableTestPulse(False)
            self.dev.pressureDevice.setSource('atmosphere')

    def quit(self):
        disconnect(self.dev.sigTestPulseFinished, self.testPulseFinished)
        disconnect(self.dev.sigGlobalTransformChanged, self.transformChanged)
        disconnect(self.dev.sigStateChanged, self.stateChanged)
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

    def startJob(self, jobType, *args, **kwds):
        self.stopJob()
        jobClass = self.jobTypes[jobType]
        job = jobClass(self.dev, *args, **kwds)
        self.currentJob = job
        job.sigStateChanged.connect(self.jobStateChanged)
        job.sigFinished.connect(self.jobFinished)
        return job

    def jobStateChanged(self, job, state):
        self.dev.logEvent("stateManagerEvent", info=state)

    def jobFinished(self, job):
        disconnect(job.sigStateChanged, self.jobStateChanged)
        disconnect(job.sigFinished, self.jobFinished)
        if job.nextState is not None:
            self.requestStateChange(job.nextState)

    def cleanPipette(self):
        config = self.dev.config.get('cleaning', {})
        return self.startJob('clean', dev=self.dev, config=config)

    def startApproach(self, speed):
        config = {'initialMoveSpeed': speed}
        return self.startJob('approach', dev=self.dev, config=config)
