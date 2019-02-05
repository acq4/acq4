from __future__ import print_function
import threading
import time
import numpy as np
import scipy.stats
try:
    import queue
except ImportError:
    import Queue as queue
from acq4.pyqtgraph import ptime, disconnect
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

    def initializePressure(self):
        """Set initial pressure based on the config key 'initialPressure'
        """
        pressure = self.config.get('initialPressure')
        if pressure is None:
            return
        
        self.dev.setPressure(pressure)

    def initializeClamp(self):
        """Set initial clamp parameters based on the config keys
        'initialClampMode', 'initialClampHolding', and 'initialTestPulseEnable'.
        """
        cdev = self.dev.clampDevice
        mode = self.config.get('initialClampMode')
        holding = self.config.get('initialClampHolding')
        tp = self.config.get('initialTestPulseEnable')

        if mode is not None:
            cdev.setMode(mode)
            if holding is not None:
                cdev.setHolding(value=holding)

        # enable test pulse if config requests it AND the device is "active"
        if tp is not None:
            self.dev.enableTestPulse(tp and self.dev.active)

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
        raise NotImplementedError()

    def cleanup(self, interrupted):
        """Called after job completes, whether it failed or succeeded.
        """
        pass

    def _runJob(self):
        """Function invoked in background thread.

        This calls the custom run() method for the state subclass and handles the possible
        error / exit / completion states.
        """
        try:
            # run must be reimplemented in subclass and call self._checkStop() frequently
            self.nextState = self.run()

        except self.StopRequested:
            # state was stopped early by calling stop()
            interrupted = True
            error = None
        except Exception as exc:
            # state aborted due to an error
            interrupted = True
            error = str(exc)
            printExc("Error during %s:" % self.stateName)
        else:
            # state completed successfully
            interrupted = False
            error = None
        finally:
            try:
                self.cleanup(interrupted)
            except Exception:
                printExc("Error during %s cleanup:" % self.stateName)
            disconnect(self.dev.sigTestPulseFinished, self.testPulseFinished)
            
            if not self.isDone():
                self._taskDone(interrupted=interrupted, error=error)


class PatchPipetteOutState(PatchPipetteState):
    stateName = 'out'

    def defaultConfig(self):
        return {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': False,
        }
    
    def initialize(self):
        PatchPipetteState.initialize(self)
        # assume that pipette has been changed
        self.dev.newPipette()


class PatchPipetteApproachState(PatchPipetteState):
    stateName = 'approach'

    def defaultConfig(self):
        return {
            'nextState': 'cell detect',
            'fallbackState': 'bath',
        }

    def run(self):
        # move to approach position + auto pipette offset
        fut = self.dev.goApproach('fast')
        self.dev.clampDevice.autoPipetteOffset()
        self.dev.resetTestPulseHistory()
        while not fut.isDone():
            self._checkStop()
            time.sleep(0.1)
        return self.config['nextState']


class PatchPipetteWholeCellState(PatchPipetteState):
    stateName = 'whole cell'
    def defaultConfig(self):
        return {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': -70e-3,
            'initialTestPulseEnable': True,
        }


class PatchPipetteBrokenState(PatchPipetteState):
    stateName = 'broken'
    def defaultConfig(self):
        return {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
        }


class PatchPipetteFouledState(PatchPipetteState):
    stateName = 'fouled'
    def defaultConfig(self):
        return {
            'initialPressure': None,
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
        }


class PatchPipetteBathState(PatchPipetteState):
    """Handles detection of changes while in recording chamber

    - monitor resistance to detect entry into bath
    - auto pipette offset and record initial resistance
    - monitor resistance for pipette break / clog
    """
    stateName = 'bath'
    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)

    def defaultConfig(self):
        return {
            'initialPressure': 3500.,  # 0.5 PSI
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
            'bathThreshold': 50e6,
            'breakThreshold': -1e6,
            'clogThreshold': 1e6,
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

            self.setState('bath detected' % ssr)
            bathResistances.append(ssr)

            if initialResistance is None:
                if len(bathResistances) > 8:
                    initialResistance = np.median(bathResistances)
                    self.setState('initial resistance measured: %f' % initialResistance)
                    dev.updatePatchRecord(initialBathResistance=initialResistance)
                else:
                    continue

            # check for pipette break
            if ssr < initialResistance + config['breakThreshold']:
                self.setState('broken pipette detected')
                self._taskDone(interrupted=True, error="Pipette broken")
                return 'broken'

            if ssr > initialResistance + config['clogThreshold']:
                self.setState('clogged pipette detected')
                self._taskDone(interrupted=True, error="Pipette clogged")
                return 'fouled'


class PatchPipetteCellDetectState(PatchPipetteState):
    """Handles cell detection:

    - monitor resistance for cell proximity => seal mode
    - monitor resistance for pipette break
    """
    stateName = 'cell detect'
    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)

    def defaultConfig(self):
        return {
            'initialPressure': None,
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
            'fallbackState': 'bath',
            'autoAdvance': True,
            'advanceMode': 'vertical',
            'advanceInterval': 0.5,
            'advanceStepDistance': 1e-6,
            'maxAdvanceDistance': 20e-6,
            'advanceSpeed': 32e-6,
            'fastDetectionThreshold': 1e6,
            'slowDetectionThreshold': 0.3e6,
            'slowDetectionSteps': 3,
            'breakThreshold': -1e6,
        }

    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev = self.dev
        initialResistance = None
        recentTestPulses = deque(maxlen=config['slowDetectionSteps'] + 1)
        lastMove = ptime.time() - config['advanceInterval']
        initialPosition = np.array(dev.globalPosition())
        stepCount = 0

        while True:
            self._checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            self.setState("checking test pulses")
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            recentTestPulses.extend(tps)
            tp = tps[-1]
            ssr = tp.analysis()['steadyStateResistance']
            if initialResistance is None:
                initialResistance = ssr


            # check for pipette break
            if ssr < initialResistance + config['breakThreshold']:
                self._taskDone(interrupted=True, error="Pipette broken")
                return 'broken'

            # fast cell detection
            if ssr > initialResistance + config['fastDetectionThreshold']:
                self.setState("cell detected (fast criteria)")
                self._taskDone()
                return "seal"

            # slow cell detection
            if len(recentTestPulses) > config['slowDetectionSteps']:
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                if np.all(np.diff(res) > 0) and ssr - initialResistance > config['slowDetectionThreshold']:
                    self.setState("cell detected (slow criteria)")
                    self._taskDone()
                    return "seal"

            pos = np.array(dev.globalPosition())
            dist = np.linalg.norm(pos - initialPosition)

            # fail if pipette has moved too far before detection
            if dist > config['maxAdvanceDistance']:
                self._taskDone(interrupted=True, error="No cell found within maximum search distance")
                return None

            # advance to next position
            self._checkStop()
            self.setState("advancing pipette")
            if config['advanceMode'] == 'vertical':
                stepPos = initialPosition + (stepCount + 1) * np.array([0, 0, -config['advanceStepDistance']])
            elif config['advanceMode'] == 'axial':
                stepPos = initialPosition + dev.globalDirection() * (stepCount + 1) * config['advanceStepDistance']
            elif config['advanceMode'] == 'target':
                targetPos = np.array(dev.targetPosition())
                targetVector = targetPos - pos
                stepPos = pos + config['advanceStepDistance'] * targetVector / np.linalg.norm(targetVector)
            else:
                raise ValueError("advanceMode must be 'vertical', 'axial', or 'target'  (got %r)" % config['advanceMode'])
            fut = dev._moveToGlobal(stepPos, speed=config['advanceSpeed'])
            while True:
                self._checkStop()
                fut.wait(timeout=0.2)
                if fut.isDone():
                    stepCount += 1
                    break


class PatchPipetteSealState(PatchPipetteState):
    """Handles sealing onto cell

    - monitor resistance to detect loose seal and GOhm seal
    - set holding potential after loose seal
    - modulate pressure to improve likelihood of forming seal
    - cut pressure after GOhm and transition to cell attached
    """
    stateName = 'seal'
    def __init__(self, *args, **kwds):
        PatchPipetteState.__init__(self, *args, **kwds)

    def defaultConfig(self):
        return {
            'initialPressure': None,
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
            'pressureMode': 'auto',   # 'auto' or 'user'
            'holdingThreshold': 100e6,
            'holdingPotential': -70e-3,
            'sealThreshold': 1e9,
            'nSlopeSamples': 5,
            'autoSealTimeout': 380.0,
        }

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
        dev.updatePatchRecord(resistanceBeforeSeal=initialResistance)
        startTime = ptime.time()
        pressure = 0

        mode = config['pressureMode']
        self.setState('beginning seal (mode: %r)' % mode)
        if mode == 'user':
            dev.setPressure('user')
        elif mode == 'auto':
            dev.setPressure('atmosphere')
        else:
            raise ValueError("pressureMode must be 'auto' or 'user' (got %r')" % mode)
        
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

            if not holdingSet and ssr > config['holdingThreshold']:
                self.setState('enable holding potential %0.1f mV' % (config['holdingPotential']*1000))
                dev.clampDevice.setHolding(mode=None, value=config['holdingPotential'])
                holdingSet = True

            if ssr > config['sealThreshold']:
                dev.setPressure('atmosphere')
                self.setState('gigaohm seal detected')
                self._taskDone()
                return 'cell attached'
            
            if mode == 'auto':
                dt = ptime.time() - startTime
                if dt < 5:
                    # start with 5 seconds at atmosphereic pressure
                    continue

                if dt > config['autoSealTimeout']:
                    self._taskDone(interrupted=True, error="Seal failed after %f seconds" % dt)
                    return None

                # update pressure
                res = np.array([tp.analysis()['steadyStateResistance'] for tp in recentTestPulses])
                times = np.array([tp.startTime() for tp in recentTestPulses])
                slope = scipy.stats.linregress(times, res).slope
                if slope < 1e6: 
                    pressure -= 200
                elif slope < 100e6:
                    pass
                elif slope > 200e6:
                    pressure += 200

                pressure = np.clip(pressure, -10e3, 0)
                self.setState('Rpip slope: %g MOhm/sec   Pressure: %g Pa' % (slope/1e6, pressure))
                dev.setPressure(pressure)

    def cleanup(self, interrupted):
        self.dev.setPressure('atmosphere')



class PatchPipetteCellAttachedState(PatchPipetteState):
    stateName = 'cell attached'
    def defaultConfig(self):
        return {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': -70e-3,
            'initialTestPulseEnable': True,
            'autoBreakInDelay': 5,
            'breakInThreshold': 800e6,
            'holdingCurrentThreshold': -1e-9,
        }

    def run(self):
        self.monitorTestPulse()
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
            
            ssr = tp.analysis()['steadyStateResistance']
            if ssr < config['breakInThreshold']:
                return 'whole cell'


class PatchPipetteBreakInState(PatchPipetteState):
    stateName = 'break in'
    def defaultConfig(self):
        return {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': -70e-3,
            'initialTestPulseEnable': True,
            'nPulses': [1, 1, 1, 1, 1, 2, 2, 3, 3, 5],
            'pulseDurations': [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.7, 1.5],
            'pulsePressures': [-20e3, -25e3, -30e3, -40e3, -50e3, -60e3, -60e3, -65e3, -65e3, -65e3],
            'pulseInterval': 2,
            'breakInThreshold': 800e6,
            'holdingCurrentThreshold': -1e-9,
            'fallbackState': 'fouled',
        }

    def run(self):
        self.monitorTestPulse()
        config = self.config
        lastPulse = ptime.time()
        attempt = 0

        while True:
            status = self.checkBreakIn()
            if status is True:
                return 'whole cell'
            elif status is False:
                return

            if ptime.time() - lastPulse > config['pulseInterval']:
                nPulses = config['nPulses'][attempt]
                pdur = config['pulseDurations'][attempt]
                press = config['pulsePressures'][attempt]
                self.setState('Break in attempt %d' % attempt)
                status = self.attemptBreakIn(nPulses, pdur, press)
                if status is True:
                    return 'whole cell'
                elif status is False:
                    return
                lastPulse = ptime.time()
                attempt += 1
        
            if attempt >= len(config['nPulses']):
                self._taskDone(interrupted=True, error='Breakin failed after %d attempts' % attempt)
                return

    def attemptBreakIn(self, nPulses, duration, pressure):
        for i in range(nPulses):
            # get the next test pulse
            status = self.checkBreakIn()
            if status is not None:
                return status
            
            self.dev.setPressure(pressure)
            time.sleep(duration)
            self.dev.setPressure('atmosphere')
                
    def checkBreakIn(self):
        while True:
            self._checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) > 0:
                break
        tp = tps[-1]

        holding = tp.analysis()['baselineCurrent']
        if holding < self.config['holdingCurrentThreshold']:
            self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
            return False

        ssr = tp.analysis()['steadyStateResistance']
        if ssr < self.config['breakInThreshold']:
            return True



class PatchPipetteCleanState(PatchPipetteState):
    """Pipette cleaning state.

    Cycles +/- pressure in a "clean" bath followed by an optional "rinse" bath.
    """
    stateName = 'pipette clean'

    def defaultConfig(self):
        config = {
            'initialPressure': 'atmosphere',
            'initialClampMode': 'vc',
            'initialClampHolding': 0,
            'initialTestPulseEnable': True,
            'cleanSequence': [(-35e3, 1.0), (100e3, 1.0)] * 5,
            'rinseSequence': [(-35e3, 3.0), (100e3, 10.0)],
            'approachHeight': 5e-3,
            'cleanPos': self.dev.loadPosition('clean'),
            'rinsePos': self.dev.loadPosition('rinse', None),
        }
        return config

    def run(self):
        self.monitorTestPulse()
        # Called in worker thread
        self.resetPos = None
        config = self.config.copy()
        dev = self.dev

        dev.setState('cleaning')

        dev.retractFromSurface().wait()

        for stage in ('clean', 'rinse'):
            self._checkStop()

            sequence = config[stage + 'Sequence']
            if len(sequence) == 0:
                continue
            pos = config[stage + 'Pos']
            approachPos = [pos[0], pos[1], pos[2] + config['approachHeight']]

            dev._moveToGlobal(approachPos, 'fast').wait()
            self._checkStop()
            self.resetPos = approachPos
            dev._moveToGlobal(pos, 'fast').wait()
            self._checkStop()

            for pressure, delay in sequence:
                dev.setPressure(pressure)
                self._checkStop(delay)

    def cleanup(self, interrupted):
        dev = self.dev
        try:
            dev.setPressure(0)
        except Exception:
            printExc("Error resetting pressure after clean")
        
        if self.resetPos is not None:
            dev._moveToGlobal(self.resetPos, 'fast')
            dev.setState('out')
