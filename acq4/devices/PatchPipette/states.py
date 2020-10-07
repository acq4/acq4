from __future__ import print_function
import threading
import sys, time
import numpy as np
import scipy.stats
from six.moves import range, queue
from pyqtgraph import ptime, disconnect
from acq4.util.future import Future
from collections import deque
from acq4.util.debug import printExc


class PatchPipetteState(Future):
    """Base class for implementing the details of a patch pipette state:
    
    - Set initial pressure, clamp parameters, position, etc when starting the state
    - Optionally run a background thread; usually this will monitor pipette resistance
      and affect the pipette pressure, holding value, or position.

    This class is the base for other state subclasses classes and just takes care of some boilerplate:
     - assembling config from defaults and init args
     - set initial device state
     - starting thread (if run() method is implemented)
     - handling various job failure / finish modes
     - communicating next state transition to the state manager
    """

    # state subclasses must set a string name
    stateName = None

    # State classes may implement a run() method to be called in a background thread
    run = None

    def __init__(self, dev, config=None):
        Future.__init__(self)

        self.dev = dev

        # generate full config by combining passed-in arguments with default config
        self.config = self.defaultConfig()
        if config is not None:
            self.config.update(config)

        # indicates state that should be transitioned to next, if any.
        # This is usually set by the return value of run(), and must be invoked by the state manager.
        self.nextState = self.config.get('fallbackState', None)

    def initialize(self):
        """Initialize pressure, clamp, etc. and start background thread when entering this state.

        This method is called by the state manager.
        """
        try:
            if self.config.get('finishPatchRecord') is True:
                self.dev.finishPatchRecord()
            if self.config.get('newPipette') is True:
                self.dev.newPipette()

            self.initializePressure()
            self.initializeClamp()

            # set up test pulse monitoring
            self.testPulseResults = queue.Queue()
            
            if self.run is not None and self.dev.active:
                # start background thread if the device is "active" and the subclass has a run() method 
                self._thread = threading.Thread(target=self._runJob)
                self._thread.start()
            else:
                # otherwise, just mark the task complete
                self._taskDone(interrupted=False, error=None)
        except Exception as exc:
            self._taskDone(interrupted=True, error=str(exc))
            raise

    def initializePressure(self):
        """Set initial pressure based on the config keys 'initialPressureSource' and 'initialPressure'
        """
        if self.dev.pressureDevice is None:
            return
        pressure = self.config.get('initialPressure', None)
        source = self.config.get('initialPressureSource', None)
        self.dev.pressureDevice.setPressure(source=source, pressure=pressure)

    def initializeClamp(self):
        """Set initial clamp parameters based on the config keys
        'initialClampMode', 'initialClampHolding', and 'initialTestPulseEnable'.
        """
        cdev = self.dev.clampDevice
        if cdev is None:
            return
        mode = self.config.get('initialClampMode')
        holding = self.config.get('initialClampHolding')
        tp = self.config.get('initialTestPulseEnable')
        tpParams = self.config.get('initialTestPulseParameters')
        bias = self.config.get('initialAutoBiasEnable')
        biasTarget = self.config.get('initialAutoBiasTarget')

        if mode is not None:
            cdev.setMode(mode)
            if holding is not None:
                cdev.setHolding(mode=mode, value=holding)
            if tpParams is None:
                tpParams = {}
            tpParams.setdefault('clampMode', mode)

        # enable test pulse if config requests it AND the device is "active"
        if tp is not None:
            self.dev.enableTestPulse(tp and self.dev.active)
        if tpParams is not None:
            self.dev.setTestPulseParameters(**tpParams)

        if bias is not None:
            self.dev.enableAutoBias(bias)
        if biasTarget is not None:
            self.dev.setAutoBiasTarget(biasTarget)

    def monitorTestPulse(self):
        """Begin acquiring test pulse data in self.testPulseResults
        """
        self.dev.sigTestPulseFinished.connect(self.testPulseFinished)

    def testPulseFinished(self, pip, result):
        self.testPulseResults.put(result)

    def getTestPulses(self, timeout):
        """Get all test pulses in the queue. If no test pulses are available, then
        wait *timeout* seconds for one to arrive.
        """
        tps = []
        try:
            if timeout is not None:
                tps.append(self.testPulseResults.get(timeout=timeout))
            while not self.testPulseResults.empty():
                tps.append(self.testPulseResults.get())
        except queue.Empty:
            pass
        return tps

    def defaultConfig(self):
        """Subclasses may reimplement this method to return a default configuration dict.
        """
        return self._defaultConfig

    def cleanup(self):
        """Called after job completes, whether it failed or succeeded.
        """
        pass

    def _runJob(self):
        """Function invoked in background thread.

        This calls the custom run() method for the state subclass and handles the possible
        error / exit / completion states.
        """
        error = None
        excInfo = None
        try:
            # run must be reimplemented in subclass and call self._checkStop() frequently
            self.nextState = self.run()
            interrupted = self.wasInterrupted()
        except self.StopRequested:
            # state was stopped early by calling stop()
            interrupted = True
        except Exception as exc:
            # state aborted due to an error
            interrupted = True
            printExc("Error in %s state %s" % (self.dev.name(), self.stateName))
            error = str(exc)
            excInfo = sys.exc_info()
        else:
            # state completed successfully
            interrupted = False
        finally:
            disconnect(self.dev.sigTestPulseFinished, self.testPulseFinished)
            if not self.isDone():
                self._taskDone(interrupted=interrupted, error=error, excInfo=excInfo)

    def _checkStop(self, delay=0):
        # extend checkStop to also see if the pipette was deactivated.
        if self.dev.active is False:
            raise self.StopRequested()
        Future._checkStop(self)

    def __repr__(self):
        return '<%s "%s">' % (type(self).__name__, self.stateName)


class PatchPipetteOutState(PatchPipetteState):
    stateName = 'out'

    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': False,
        'finishPatchRecord': True,
    }


class PatchPipetteApproachState(PatchPipetteState):
    stateName = 'approach'

    _defaultConfig = {
        'nextState': 'cell detect',
        'fallbackState': 'bath',
    }

    def run(self):
        # move to approach position + auto pipette offset
        fut = self.dev.pipetteDevice.goApproach('fast')
        self.dev.clampDevice.autoPipetteOffset()
        self.dev.resetTestPulseHistory()
        self.waitFor(fut)
        return self.config['nextState']


class PatchPipetteWholeCellState(PatchPipetteState):
    stateName = 'whole cell'
    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'initialAutoBiasEnable': True,
        'initialAutoBiasTarget': -70e-3,
    }

    def run(self):
        config = self.config
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStartTime'] = ptime.time()
        patchrec['wholeCellPosition'] = tuple(self.dev.pipetteDevice.globalPosition())

        # TODO: Option to switch to I=0 for a few seconds to get initial RMP decay

        while True:
            # TODO: monitor for cell loss
            self._checkStop()
            time.sleep(0.1)

    def cleanup(self):
        patchrec = self.dev.patchRecord()
        patchrec['wholeCellStopTime'] = ptime.time()
        PatchPipetteState.cleanup(self)


class PatchPipetteBrokenState(PatchPipetteState):
    stateName = 'broken'
    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'finishPatchRecord': True,
    }

    def initialize(self):
        self.dev.setTipBroken(True)
        PatchPipetteState.initialize(self)


class PatchPipetteFouledState(PatchPipetteState):
    stateName = 'fouled'
    _defaultConfig = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
    }

    def initialize(self):
        self.dev.setTipClean(False)
        PatchPipetteState.initialize(self)


class PatchPipetteBathState(PatchPipetteState):
    """Handles detection of changes while in recording chamber

    - monitor resistance to detect entry into bath
    - auto pipette offset and record initial resistance
    - monitor resistance for pipette break / clog
    """
    stateName = 'bath'
    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)

    _defaultConfig = {
        'initialPressure': 3500.,  # 0.5 PSI
        'initialPressureSource': 'regulator',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'bathThreshold': 50e6,
        'breakThreshold': -1e6,
        'clogThreshold': 1e6,
        'targetDistanceThreshold': 10e-6
    }
    
    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev = self.dev
        initialResistance = None
        bathResistances = []

        while True:
            self._checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            
            tp = tps[-1]  # if we're falling behind, just skip the extra test pulses

            ssr = tp.analysis()['steadyStateResistance']
            if ssr > config['bathThreshold']:
                # not in bath yet
                bathResistances = []
                continue

            bathResistances.append(ssr)

            if initialResistance is None:
                if len(bathResistances) > 8:
                    initialResistance = np.median(bathResistances)
                    self.setState('initial resistance measured: %0.2f MOhm' % (initialResistance * 1e-6))

                    # record initial resistance
                    patchrec = dev.patchRecord()
                    patchrec['initialBathResistance'] = initialResistance
                    piprec = dev.pipetteRecord()
                    if piprec['originalResistance'] is None:
                        piprec['originalResistance'] = initialResistance
                        patchrec['originalPipetteResistance'] = initialResistance

                else:
                    continue

            # check for pipette break
            if ssr < initialResistance + config['breakThreshold']:
                self.setState('broken pipette detected')
                self._taskDone(interrupted=True, error="Pipette broken")
                return 'broken'

            # if close to target, switch to cell detect
            # pos = dev.globalPosition()
            # target = dev.

            if ssr > initialResistance + config['clogThreshold']:
                self.setState('clogged pipette detected')
                self._taskDone(interrupted=True, error="Pipette clogged")
                return 'fouled'


class PatchPipetteCellDetectState(PatchPipetteState):
    """Handles cell detection:

    - monitor resistance for cell proximity => seal mode
    - monitor resistance for pipette break

    TODO: 
    - Obstacle avoidance
    """
    stateName = 'cell detect'
    def __init__(self, *args, **kwds):
        self.contAdvanceFuture = None
        self.lastMove = 0.0
        self.stepCount = 0
        self.advanceSteps = None
        PatchPipetteState.__init__(self, *args, **kwds)

    _defaultConfig = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
        'autoAdvance': True,
        'advanceMode': 'target',
        'advanceContinuous': True,
        'advanceStepInterval': 0.1,
        'advanceStepDistance': 1e-6,
        'maxAdvanceDistance': None,
        'maxAdvanceDistancePastTarget': 10e-6,
        'maxAdvanceDepthBelowSurface': None,
        'advanceSpeed': 2e-6,
        'fastDetectionThreshold': 1e6,
        'slowDetectionThreshold': 0.2e6,
        'slowDetectionSteps': 3,
        'breakThreshold': -1e6,
    }

    def run(self):

        self.monitorTestPulse()

        config = self.config
        dev = self.dev
        dev.clampDevice.autoPipetteOffset()

        patchrec = dev.patchRecord()
        patchrec['attemptedCellDetect'] = True
        initialResistance = None
        recentTestPulses = deque(maxlen=config['slowDetectionSteps'] + 1)
        initialPosition = np.array(dev.pipetteDevice.globalPosition())
        patchrec['cellDetectInitialTarget'] = tuple(dev.pipetteDevice.targetPosition())

        while True:
            self._checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue
            recentTestPulses.extend(tps)

            tp = tps[-1]
            ssr = tp.analysis()['steadyStateResistance']
            if initialResistance is None:
                # take note of initial resistance
                initialResistance = ssr

            # check for pipette break
            if ssr < initialResistance + config['breakThreshold']:
                self._taskDone(interrupted=True, error="Pipette broken")
                patchrec['detectedCell'] = False
                return 'broken'

            # fast cell detection
            if ssr > initialResistance + config['fastDetectionThreshold']:
                self.setState("cell detected (fast criteria)")
                self._taskDone()
                patchrec['detectedCell'] = True
                return "seal"

            # slow cell detection
            if len(recentTestPulses) > config['slowDetectionSteps']:
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                if np.all(np.diff(res) > 0) and ssr - initialResistance > config['slowDetectionThreshold']:
                    self.setState("cell detected (slow criteria)")
                    self._taskDone()
                    patchrec['detectedCell'] = True
                    return "seal"

            self._checkStop()

            if config['advanceContinuous']:
                # Start continuous move if needed
                if self.contAdvanceFuture is None:
                    print(initialPosition)
                    print(self.getSearchEndpoint())
                    self.startContinuousMove()
                if self.contAdvanceFuture.isDone():
                    self.contAdvanceFuture.wait()  # check for move errors
                    self._taskDone(interrupted=True, error="No cell found before end of search path")
                    patchrec['detectedCell'] = False
                    return config['fallbackState']
            else:
                # advance to next position if stepping
                if self.advanceSteps is None:
                    self.advanceSteps = self.getAdvanceSteps()
                    print(len(self.advanceSteps))
                    print(self.advanceSteps)
                if self.stepCount >= len(self.advanceSteps):
                    self._taskDone(interrupted=True, error="No cell found before end of search path")
                    patchrec['detectedCell'] = False
                    return config['fallbackState']
                
                # make sure we obey advanceStepInterval
                now = ptime.time()
                if now - self.lastMove < config['advanceStepInterval']:
                    continue
                self.lastMove = now

                self.singleStep()

    def getSearchEndpoint(self):
        """Return the final position along the pipette search path, taking into account 
        maxAdvanceDistance, maxAdvanceDepthBelowSurface, and maxAdvanceDistancePastTarget.
        """
        config = self.config
        dev = self.dev
        pip = dev.pipetteDevice
        pos = np.array(pip.globalPosition())
        surface = pip.scopeDevice().getSurfaceDepth()
        target = np.array(pip.targetPosition())

        # what direction are we moving?
        if config['advanceMode'] == 'vertical':
            direction = np.array([0.0, 0.0, -1.0])
        elif config['advanceMode'] == 'axial':
            direction = pip.globalDirection()
        elif config['advanceMode'] == 'target':
            direction = target - pos
        else:
            raise ValueError("advanceMode must be 'vertical', 'axial', or 'target'  (got %r)" % config['advanceMode'])
        direction = direction / np.linalg.norm(direction)

        endpoint = None

        # max search distance
        if config['maxAdvanceDistance'] is not None:
            endpoint = pos + direction * config['maxAdvanceDistance']            

        # max surface depth 
        if config['maxAdvanceDepthBelowSurface'] is not None and direction[2] < 0:
            endDepth = surface - config['maxAdvanceDepthBelowSurface']
            dz = endDepth - pos[2]
            depthEndpt = pos + direction * (dz / direction[2])
            # is the surface depth endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(depthEndpt-pos):
                endpoint = depthEndpt

        # max distance past target
        if config['advanceMode'] == 'target' and config['maxAdvanceDistancePastTarget'] is not None:
            targetEndpt = target + direction * config['maxAdvanceDistancePastTarget']
            # is the target endpoint closer?
            if endpoint is None or np.linalg.norm(endpoint-pos) > np.linalg.norm(targetEndpt-pos):
                endpoint = targetEndpt

        if endpoint is None:
            raise Exception("Cell detect state requires one of maxAdvanceDistance, maxAdvanceDepthBelowSurface, or maxAdvanceDistancePastTarget.")

        return endpoint

    def startContinuousMove(self):
        """Begin moving pipette continuously along search path.
        """
        endpoint = self.getSearchEndpoint()
        self.contAdvanceFuture = self.dev.pipetteDevice._moveToGlobal(endpoint, speed=self.config['advanceSpeed'])

    def getAdvanceSteps(self):
        """Return the list of step positions to take along the search path.
        """
        config = self.config
        endpoint = self.getSearchEndpoint()
        pos = np.array(self.dev.pipetteDevice.globalPosition())
        diff = endpoint - pos
        dist = np.linalg.norm(diff)
        nSteps = int(dist / config['advanceStepDistance'])
        step = diff * config['advanceStepDistance'] / dist
        return pos[np.newaxis, :] + step[np.newaxis, :] * np.arange(nSteps)[:, np.newaxis]

    def singleStep(self):
        """Advance a single step in the search path and block until the move has finished.
        """
        config = self.config
        dev = self.dev

        stepPos = self.advanceSteps[self.stepCount]
        self.stepCount += 1
        fut = dev.pipetteDevice._moveToGlobal(stepPos, speed=config['advanceSpeed'])
        self.waitFor(fut)

    def cleanup(self):
        if self.contAdvanceFuture is not None:
            self.contAdvanceFuture.stop()
        patchrec = self.dev.patchRecord()
        patchrec['cellDetectFinalTarget'] = tuple(self.dev.pipetteDevice.targetPosition())
        PatchPipetteState.cleanup(self)


class PatchPipetteSealState(PatchPipetteState):
    """Handles sealing onto cell

    State name: "seal"

    - monitor resistance to detect loose seal and GOhm seal
    - set holding potential after loose seal
    - modulate pressure to improve likelihood of forming seal
    - cut pressure after GOhm and transition to cell attached

    Parameters
    ----------
    pressureMode : str
        'auto' enables automatic pressure control during sealing; 
        'user' simply switches to user control for sealing.
    startingPressure : float
        Initial pressure (Pascals) to apply when beginning sealing in 'auto' mode.
    holdingThreshold : float
        Seal resistance (ohms) above which the holding potential will switch 
        from its initial value to the value specified in the *holdingPotential*
        parameter.
    holdingPotential : float
        Holding potential (volts) to apply to the pipette after the seal resistance
        becomes greater than *holdingThreshold*.
    sealThreshold : float
        Seal resistance (ohms) above which the pipette is considered sealed and
        transitions to the 'cell attached' state.
    breakInThreshold : float
        Capacitance (Farads) above which the pipette is considered to be whole-cell and 
        transitions to the 'break in' state (in case of partial break-in, we don't want to transition
        directly to 'whole cell' state).
    nSlopeSamples : int
        Number of consecutive test pulse measurements over which the rate of change
        in seal resistance is measured (for automatic pressure control).
    autoSealTimeout : float
        Maximum timeout (seconds) before the seal attempt is aborted, 
        transitioning to *fallbackState*.
    maxVacuum : float
        The largest vacuum pressure (pascals, negative value) to apply during sealing.
        When this pressure is reached, the pressure is reset to 0 and the ramp starts over after a delay.
    pressureChangeRates : list
        A list of (seal_resistance_threshold, pressure_change) tuples that determine how much to
        change the current seal pressure based on the rate of change in seal resistance.
        For each iteration, select the first tuple in the list where the current rate of
        change in seal resistance is _less_ than the threshold specified in the tuple.
    delayBeforePressure : float
        Wait time (seconds) at beginning of seal state before applying negative pressure.
    delayAfterSeal : float
        Wait time (seconds) after GOhm seal is acquired, before transitioning to next state.
    afterSealPressure : float
        Pressure (Pascals) to apply during *delayAfterSeal* interval. This can help to stabilize the seal after initial formamtion.
    resetDelay : float
        Wait time (seconds) after maxVacuum is reached, before restarting pressure ramp.

    """
    stateName = 'seal'

    _defaultConfig = {
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'fouled',
        'pressureMode': 'user',   # 'auto' or 'user'
        'startingPressure': -1000,
        'holdingThreshold': 100e6,
        'holdingPotential': -70e-3,
        'sealThreshold': 1e9,
        'breakInThreshold': 10e-12,
        'nSlopeSamples': 5,
        'autoSealTimeout': 30.0,
        'maxVacuum': -3e3, #changed from -7e3
        'pressureChangeRates': [(0.5e6, -100), (100e6, 0), (-1e6, 200)], #initially 1e6,150e6,None
        'delayBeforePressure': 0.0,
        'delayAfterSeal': 5.0,
        'afterSealPressure': -1000,
        'resetDelay': 5.0,
    }

    def initialize(self):
        self.dev.clean = False
        PatchPipetteState.initialize(self)

    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev = self.dev

        recentTestPulses = deque(maxlen=config['nSlopeSamples'])
        while True:
            initialTP = dev.lastTestPulse()
            if initialTP is not None:
                break
            self._checkStop()
            time.sleep(0.05)
        
        initialResistance = initialTP.analysis()['steadyStateResistance']
        patchrec = dev.patchRecord()
        patchrec['resistanceBeforeSeal'] = initialResistance
        patchrec['capacitanceBeforeSeal'] = initialTP.analysis()['capacitance']
        startTime = ptime.time()
        pressure = config['startingPressure']

        mode = config['pressureMode']
        self.setState('beginning seal (mode: %r)' % mode)
        if mode == 'user':
            dev.pressureDevice.setPressure(source='user', pressure=0)
        elif mode == 'auto':
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        else:
            raise ValueError("pressureMode must be 'auto' or 'user' (got %r')" % mode)

        dev.setTipClean(False)

        patchrec['attemptedSeal'] = True
        holdingSet = False

        while True:
            self._checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)            
            recentTestPulses.extend(tps)
            if len(tps) == 0:
                continue
            tp = tps[-1]

            ssr = tp.analysis()['steadyStateResistance']
            cap = tp.analysis()['capacitance']
            # if cap > config['breakInThreshold']:
            #     patchrec['spontaneousBreakin'] = True
            #     return 'break in'

            patchrec['resistanceBeforeBreakin'] = ssr
            patchrec['capacitanceBeforeBreakin'] = cap

            if not holdingSet and ssr > config['holdingThreshold']:
                self.setState('enable holding potential %0.1f mV' % (config['holdingPotential']*1000))
                dev.clampDevice.setHolding(mode=None, value=config['holdingPotential'])
                holdingSet = True

            # seal detected? 
            if ssr > config['sealThreshold']:
                # delay for a short period, possibly applying pressure to allow seal to stabilize
                if config['delayAfterSeal'] > 0:
                    if config['afterSealPressure'] == 0:
                        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                    else:
                        dev.pressureDevice.setPressure(source='regulator', pressure=config['afterSealPressure'])
                    self.sleep(config['delayAfterSeal'])

                dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                self.setState('gigaohm seal detected')

                dev.clampDevice.autoCapComp()

                self._taskDone()
                patchrec['sealSuccessful'] = True
                return 'cell attached'
            
            if mode == 'auto':
                dt = ptime.time() - startTime
                if dt < config['delayBeforePressure']:
                    # delay at atmospheric pressure before starting suction
                    continue

                if dt > config['autoSealTimeout']:
                    patchrec['sealSuccessful'] = False
                    self._taskDone(interrupted=True, error="Seal failed after %f seconds" % dt)
                    return

                # update pressure
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                times = np.array([tp.startTime() for tp in recentTestPulses])
                slope = scipy.stats.linregress(times, res).slope
                pressure = np.clip(pressure, config['maxVacuum'], 0)
                
                # decide how much to adjust pressure based on rate of change in seal resistance
                for max_slope, change in config['pressureChangeRates']:
                    if max_slope is None or slope < max_slope:
                        pressure += change
                        break
                
                # here, if the maxVacuum has been achieved and we are still sealing, cycle back to 0 and redo the pressure change
                if pressure <= config['maxVacuum']:
                    dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
                    self.sleep(config['resetDelay'])
                    pressure = 0
                    dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                    continue

                self.setState('Rpip slope: %g MOhm/sec   Pressure: %g Pa' % (slope/1e6, pressure))
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)

    def cleanup(self):
        self.dev.pressureDevice.setPressure(source='atmosphere')
        PatchPipetteState.cleanup(self)


class PatchPipetteCellAttachedState(PatchPipetteState):
    """Pipette in cell-attached configuration

    State name: "cell attached"

    - automatically transition to 'break in' after a delay
    - monitor for spontaneous break-in or loss of attached cell

    Parameters
    ----------
    autoBreakInDelay : float
        Delay time (seconds) before transitioning to 'break in' state
    breakInThreshold : float
        Capacitance (Farads) above which the pipette is considered to be whole-cell and immediately
        transitions to the 'break in' state (in case of partial break-in, we don't want to transition
        directly to 'whole cell' state).
    holdingCurrentThreshold : float
        Holding current (Amps) below which the cell is considered to be lost and the state fails.
    """
    stateName = 'cell attached'
    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'autoBreakInDelay': None,
        'breakInThreshold': 10e-12,
        'holdingCurrentThreshold': -1e-9,
    }

    def run(self):
        self.monitorTestPulse()
        patchrec = self.dev.patchRecord()
        config = self.config
        startTime = ptime.time()
        delay = config['autoBreakInDelay']
        while True:
            if delay is not None and ptime.time() - startTime > delay:
                return 'break in'

            self._checkStop()

            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            tp = tps[-1]
            holding = tp.analysis()['baselineCurrent']
            if holding < self.config['holdingCurrentThreshold']:
                self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
                return
            
            cap = tp.analysis()['capacitance']
            # if cap > config['breakInThreshold']:
            #     patchrec['spontaneousBreakin'] = True
            #     return 'break in'

            patchrec['resistanceBeforeBreakin'] = tp.analysis()['steadyStateResistance']
            patchrec['capacitanceBeforeBreakin'] = cap


class PatchPipetteBreakInState(PatchPipetteState):
    """State using pressure pulses to rupture membrane for whole cell recording.

    State name: "break in"

    - applies a sequence of pressure pulses of increasing strength
    - monitors for break-in

    Parameters
    ----------
    nPulses : list of int
        Number of pressure pulses to apply on each break-in attempt
    pulseDurations : list of float
        Duration (seconds) of pulses to apply on each break in attempt
    pulsePressures : list of float
        Pressure (Pascals) of pulses to apply on each break in attempt
    pulseInterval : float
        Delay (seconds) between break in attempts
    capacitanceThreshold : float
        Capacitance (Farads) above which to transition to the 'whole cell' state
        (note that resistance threshold must also be met)
    resistanceThreshold : float
        Resistance (Ohms) below which to transition to the 'whole cell' state if 
        capacitance threshold is met, or fail otherwise.
    holdingCurrentThreshold : float
        Holding current (Amps) below which the cell is considered to be lost and the state fails.
    """
    stateName = 'break in'
    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': -70e-3,
        'initialTestPulseEnable': True,
        'nPulses': [1, 1, 1, 1, 1, 2, 2, 3, 3, 5],
        'pulseDurations': [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.7, 1.5],
        'pulsePressures': [-30e3, -35e3, -40e3, -50e3, -60e3, -60e3, -60e3, -60e3, -60e3, -60e3],
        'pulseInterval': 2,
        'resistanceThreshold': 650e6,
        'capacitanceThreshold': 10e-12,
        'holdingCurrentThreshold': -1e-9,
        'fallbackState': 'fouled',
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        config = self.config
        lastPulse = ptime.time()
        attempt = 0

        while True:
            status = self.checkBreakIn()
            if status is True:
                patchrec['spontaneousBreakin'] = True
                patchrec['breakinSuccessful'] = True
                return 'whole cell'
            elif status is False:
                return

            if ptime.time() - lastPulse > config['pulseInterval']:
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.setState('Break in attempt %d' % attempt)
                status = self.attemptBreakIn(nPulses, pdur, press)
                patchrec['attemptedBreakin'] = True
                if status is True:
                    patchrec['breakinSuccessful'] = True
                    patchrec['spontaneousBreakin'] = False
                    return 'whole cell'
                elif status is False:
                    patchrec['breakinSuccessful'] = False
                    return config['fallbackState']
                lastPulse = ptime.time()
                attempt += 1
        
            if attempt >= len(config['nPulses']):
                self._taskDone(interrupted=True, error='Breakin failed after %d attempts' % attempt)
                patchrec['breakinSuccessful'] = False
                return config['fallbackState']

    def attemptBreakIn(self, nPulses, duration, pressure):
        for i in range(nPulses):
            # get the next test pulse
            status = self.checkBreakIn()
            if status is not None:
                return status
            self.dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            time.sleep(duration)
            self.dev.pressureDevice.setPressure(source='atmosphere')
                
    def checkBreakIn(self):
        while True:
            self._checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
        tp = tps[-1]

        analysis = tp.analysis()
        holding = analysis['baselineCurrent']
        if holding < self.config['holdingCurrentThreshold']:
            self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
            return False

        # If ssr and cap cross threshold => successful break in
        # If only ssr crosses threshold => lost cell
        # If only cap crosses threshold => partial break in, keep trying
        ssr = analysis['steadyStateResistance']
        cap = analysis['capacitance']
        if self.config['resistanceThreshold'] is not None and ssr < self.config['resistanceThreshold']:
            return True
            # if cap > self.config['capacitanceThreshold']:
            #     return True
            # else:
            #     self._taskDone(interrupted=True, error="Resistance dropped below threshold but no cell detected.")
            #     return False

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        PatchPipetteState.cleanup(self)


class PatchPipetteResealState(PatchPipetteState):
    stateName = 'reseal'

    _defaultConfig = {
        'fallbackState': 'whole cell',
    }

    def run(self):
        # move to approach position + auto pipette offset
        pass


class PatchPipetteBlowoutState(PatchPipetteState):
    stateName = 'blowout'
    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': True,
        'blowoutPressure': 65e3,
        'blowoutDuration': 2.0,
        'fallbackState': 'bath',
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        config = self.config

        fut = self.dev.pipetteDevice.retractFromSurface()
        self.waitFor(fut)

        self.dev.pressureDevice.setPressure(source='regulator', pressure=config['blowoutPressure'])
        self.sleep(config['blowoutDuration'])
        self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        # wait until we have a test pulse that ran after blowout was finished.
        start = ptime.time()
        while True:
            self._checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0 or tps[-1].startTime() < start:
                continue
            break

        tp = tps[-1].analysis()
        patchrec['resistanceAfterBlowout'] = tp['steadyStateResistance']
        self.dev.finishPatchRecord()
        return config['fallbackState']
        
    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after blowout")
        PatchPipetteState.cleanup(self)


class PatchPipetteCleanState(PatchPipetteState):
    """Pipette cleaning state.

    Cycles +/- pressure in a "clean" bath followed by an optional "rinse" bath.
    """
    stateName = 'pipette clean'

    _defaultConfig = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialClampHolding': 0,
        'initialTestPulseEnable': False,
        'cleanSequence': [(-35e3, 1.0), (100e3, 1.0)] * 5,
        'rinseSequence': [(-35e3, 3.0), (100e3, 10.0)],
        'approachHeight': 5e-3,
        'fallbackState': 'out',
        'finishPatchRecord': True,
    }

    def __init__(self, *args, **kwds):
        self.resetPos = None
        self.lastApproachPos = None

        PatchPipetteState.__init__(self, *args, **kwds)

    def run(self):
        self.monitorTestPulse()

        config = self.config.copy()
        dev = self.dev

        self.setState('cleaning')

        dev.pipetteDevice.retractFromSurface().wait()

        for stage in ('clean', 'rinse'):
            self._checkStop()

            sequence = config[stage + 'Sequence']
            if len(sequence) == 0:
                continue

            pos = dev.pipetteDevice.loadPosition(stage)
            if pos is None:
                raise Exception("Device %s does not have a stored %s position." % (dev.pipetteDevice.name(), stage))

            self.gotoApproachPosition(pos)

            # todo: if needed, we can check TP for capacitance changes here
            # and stop moving as soon as the fluid is detected
            self.waitFor([dev.pipetteDevice._moveToGlobal(pos, 'fast')])

            for pressure, delay in sequence:
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                self._checkStop(delay)

        dev.pipetteRecord()['cleanCount'] += 1
        dev.clean = True
        self.resetPosition()
        dev.newPatchAttempt()
        return 'out'          

    def gotoApproachPosition(self, pos):
        """
        """
        dev = self.dev
        currentPos = dev.pipetteDevice.globalPosition()

        # first move back in x and up in z, leaving y unchanged
        approachPos1 = [pos[0], currentPos[1], pos[2] + self.config['approachHeight']]
        fut = dev.pipetteDevice._moveToGlobal(approachPos1, 'fast')
        self.waitFor(fut)
        if self.resetPos is None:
            self.resetPos = approachPos1

        # now move y over the well
        approachPos2 = [pos[0], pos[1], pos[2] + self.config['approachHeight']]
        fut = dev.pipetteDevice._moveToGlobal(approachPos2, 'fast')
        self.lastApproachPos = approachPos2
        self.waitFor(fut)

    def resetPosition(self):
        if self.lastApproachPos is not None:
            self.dev.pipetteDevice._moveToGlobal(self.lastApproachPos, 'fast').wait()
            self.lastApproachPos = None
        if self.resetPos is not None:
            self.dev.pipetteDevice._moveToGlobal(self.resetPos, 'fast').wait()
            self.resetPos = None

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")
        
        self.resetPosition()
            
        PatchPipetteState.cleanup(self)
