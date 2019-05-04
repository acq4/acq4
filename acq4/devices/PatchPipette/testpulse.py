from __future__ import print_function
import time, threading
import numpy as np
from acq4.pyqtgraph import ptime
from ...Manager import getManager
from acq4.util import Qt
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
from acq4.util.debug import printExc


class TestPulseThread(Thread):
    """Background thread that runs periodic test pulses on a single patch clamp channel.
    """

    sigTestPulseFinished = Qt.Signal(object, object)  # device, result

    class StopRequested(Exception):
        pass

    def __init__(self, dev, params):
        Thread.__init__(self, name="TestPulseThread(%s)"%dev.name())
        self.dev = dev
        self._stop = False
        self.params = {
            'testPulseClass': TestPulse,
            'clampMode': None,
            'interval': None,
            'autoBiasEnabled': True,
            'autoBiasTarget': -70e-3,  # if None, use VC holding
            'autoBiasFollowRate': 0.5,
            'autoBiasMinCurrent': -1.5e-9,
            'autoBiasMaxCurrent': 1.5e9,
            'autoBiasVCCarryover': 0.7,
            'sampleRate': 500000,
            'downsample': 20,
            'vcPreDuration': 5e-3,
            'vcPulseDuration': 10e-3,
            'vcPostDuration': 5e-3,
            'vcHolding': None,
            'vcAmplitude': -10e-3,
            'vcAverage': 4,
            'icPreDuration': 10e-3,
            'icPulseDuration': 80e-3,
            'icPostDuration': 80e-3,
            'icHolding': None,
            'icAmplitude': -10e-12,
            'icAverage': 4,
            '_index': 0,
        }
        self._lastTask = None

        self._clampDev = self.dev.clampDevice
        self._daqName = list(self._clampDev.listChannels().values())[0]['device']  ## Just guess the DAQ by checking one of the clamp's channels
        self._clampName = self._clampDev.name()
        self._manager = getManager()

        self.setParameters(**params)

    def setParameters(self, **kwds):
        newParams = self.params.copy()
        for k,v in kwds.items():
            if k not in self.params:
                raise KeyError("Unknown parameter %s" % k)
            newParams[k] = v
        newParams['_index'] += 1
        self.params = newParams

    def getParameter(self, param):
        return self.params[param]

    def start(self):
        self._stop = False
        Thread.start(self)

    def stop(self, block=False):
        self._stop = True
        if block:
            if not self.wait(10000):
                raise RuntimeError("Timed out waiting for test pulse thread exit.")
                
    def run(self):
        while True:
            try:
                self._checkStop()
                start = ptime.time()
                self.runOnce(_checkStop=True)

                interval = self.params['interval']
                if interval is None:
                    # start again immediately
                    continue
                
                # otherwise, wait until interval is over
                while True:
                    nextRun = start + self.params['interval']
                    now = ptime.time()
                    if now >= nextRun:
                        break
                    time.sleep(min(0.03, nextRun-now))
                    self._checkStop()
            except self.StopRequested:
                break
            except Exception:
                printExc("Error in test pulse thread:")
                time.sleep(2.0)

    def runOnce(self, _checkStop=False):
        currentMode = self._clampDev.getMode()
        params = self.params
        runMode = currentMode if params['clampMode'] is None else params['clampMode']
        if runMode == 'I=0':
            runMode = 'IC'

        # Can't reuse tasks yet; remove this when we can.
        self._lastTask = None

        if self._lastTask is None or self._lastTask._paramIndex != params['_index'] or self._lastTask._clampMode != runMode:
            taskParams = params.copy()

            # select parameters to use based on clamp mode
            for k in params:
                # rename like icPulseDuration => pulseDuration
                if k[:2] == runMode.lower():
                    taskParams[k[2].lower() + k[3:]] = taskParams[k]
                # remove all ic__ and vc__ params
                if k[:2] in ('ic', 'vc'):
                    taskParams.pop(k)
                taskParams['clampMode'] = runMode

            task = self.createTask(taskParams)
            task._paramIndex = params['_index']
            task._clampMode = runMode
            self._lastTask = task
            self._lastTaskParams = taskParams
        else:
            task = self._lastTask
            taskParams = self._lastTaskParams
        
        # if clamp mode changed while we were fiddling around, then abort.
        task.reserveDevices()
        try:
            if self._clampDev.getMode() != currentMode:
                task.releaseDevices()
                return
            
            task.execute()
                
            while not task.isDone():
                if _checkStop:
                    self._checkStop()
                time.sleep(0.01)
        
            tp = None
            if params['autoBiasEnabled']:
                # update bias before unlocking
                result = task.getResult()
                tp = self._makeTpResult(taskParams, result)
                self.updateAutoBias(tp)
        finally:
            task.releaseDevices()

        if tp is None:
            # no auto bias, release before doing analysis
            result = task.getResult()
            tp = self._makeTpResult(taskParams, result)

        self.sigTestPulseFinished.emit(self.dev, tp)

    def _makeTpResult(self, taskParams, result):
        tpClass = taskParams['testPulseClass']
        tp = tpClass(self._clampDev, taskParams, result)
        tp.analysis()
        return tp

    def createTask(self, params):
        duration = params['preDuration'] + params['pulseDuration'] + params['postDuration']
        numPts = int(float(duration * params['sampleRate']) * params['downsample']) // params['downsample']
        params['numPts'] = numPts  # send this back for analysis
        mode = params['clampMode']

        cmdData = np.empty(numPts * params['average'])
        holding = params['holding'] or self._clampDev.getHolding(mode)
        cmdData[:] = holding

        for i in range(params['average']):
            start = (numPts * i) + int(params['preDuration'] * params['sampleRate'])
            stop = start + int(params['pulseDuration'] * params['sampleRate'])
            cmdData[start:stop] += params['amplitude']
        
        cmd = {
            'protocol': {'duration': duration * params['average']},
            self._daqName: {'rate': params['sampleRate'], 'numPts': numPts * params['average'], 'downsample': params['downsample']},
            self._clampName: {
                'mode': mode,
                'command': cmdData,
                'recordState': ['BridgeBalResist', 'BridgeBalEnable'],
            }
        }
        if params['holding'] is not None:
            cmd[self._clampName]['holding'] = params['holding']

        return self._manager.createTask(cmd)

    def _checkStop(self):
        if self._stop:
            raise self.StopRequested()

    def updateAutoBias(self, tp):
        analysis = tp.analysis()
        mode = tp.clampMode()
        if mode.lower() == 'vc':
            # set ic holding from baseline current, multiplied by some factor for a little more added safety.
            self.dev.clampDevice.setHolding('IC', analysis['baselineCurrent'] * self.params['autoBiasVCCarryover'])
        else:
            target = self.params['autoBiasTarget']
            if target is None:
                target = self.params['vcHolding']

            rm = np.clip(analysis['steadyStateResistance'], 1e6, 10e9)
            vm = analysis['baselinePotential']

            dv = target - vm
            di = dv / rm

            holding = self.dev.clampDevice.getHolding(mode)
            newHolding = holding + di * self.params['autoBiasFollowRate']
            newHolding = np.clip(newHolding, self.params['autoBiasMinCurrent'], self.params['autoBiasMaxCurrent'])

            self.dev.clampDevice.setHolding(mode, newHolding)


class TestPulse(object):
    """Represents a single test pulse run, used to analyze and extract features.
    """
    def __init__(self, dev, taskParams, result):
        self.dev = dev
        self.devName = dev.name()
        self.taskParams = taskParams
        self.result = result
        self._analysis = None
        self._analysisLock = Mutex()
        self._average = None

    @property
    def data(self):
        if self._average is None:
            params = self.taskParams
            result = self.result[self.devName]
            if params['average'] == 1:
                self._average = result
            else:
                numPts = params['numPts'] // params['downsample']
                pri = result['Channel': 'primary']
                avg = np.zeros(numPts)
                for i in range(params['average']):
                    avg += pri[i*numPts:(i+1)*numPts]
                avg /= params['average']
                self._average = result['Time':0:numPts].copy()
                self._average['Channel': 'primary']._data[:] = avg

        return self._average

    def startTime(self):
        return self.result[self.devName]._info[-1]['startTime']

    def clampMode(self):
        return self.taskParams['clampMode']

    def analysis(self):
        with self._analysisLock:
            if self._analysis is not None:
                return self._analysis
            analysis = {}
            params = self.taskParams
            pri = self.data['Channel': 'primary']

            base = pri['Time': 0:params['preDuration']]
            peak = pri['Time': params['preDuration']:params['preDuration']+2e-3]
            steady  = pri['Time': params['preDuration']:params['preDuration']+params['pulseDuration']-2e-3]
            peakValue = peak.max()
            steadyValue = np.median(steady)
            baseValue = np.median(base)

            if params['clampMode'] == 'VC':
                analysis['baselinePotential'] = params['holding'] or 0
                analysis['baselineCurrent'] = baseValue
                analysis['peakResistance'] = params['amplitude'] / (peakValue - baseValue)
                analysis['steadyStateResistance'] = np.abs(params['amplitude'] / (steadyValue - baseValue))
                if analysis['steadyStateResistance'] <= 0:
                    print("=====> ", analysis['steadyStateResistance'], params['amplitude'], steadyValue, baseValue)

            else:
                bridge = self.data._info[-1]['ClampState']['ClampParams']['BridgeBalResist']
                bridgeOn = self.data._info[-1]['ClampState']['ClampParams']['BridgeBalEnable']
                if not bridgeOn:
                    bridge = 0.0
                analysis['baselineCurrent'] = params['holding'] or 0
                analysis['baselinePotential'] = baseValue
                analysis['peakResistance'] = bridge + (peakValue - baseValue) / params['amplitude']
                analysis['steadyStateResistance'] = np.abs(bridge + (steadyValue - baseValue) / params['amplitude'])

            analysis['peakResistance'] = np.clip(analysis['peakResistance'], 0, 20e9)
            analysis['steadyStateResistance'] = np.clip(analysis['steadyStateResistance'], 0, 20e9)

            self._analysis = analysis
            return analysis
