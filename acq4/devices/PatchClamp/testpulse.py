from typing import Literal

import numpy as np
import time
from MetaArray import MetaArray

from acq4.util import Qt, ptime
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
from neuroanalysis.data import TSeries, PatchClampRecording
from neuroanalysis.test_pulse import PatchClampTestPulse
from acq4.Manager import getManager, Task
from acq4.analysis.dataModels.PatchEPhys import getBridgeBalanceCompensation
from acq4.util.functions import downsample


class TestPulseThread(Thread):
    """Background thread that runs periodic test pulses on a single patch clamp channel.
    """

    sigTestPulseFinished = Qt.Signal(object, object)  # device, result

    class StopRequested(Exception):
        pass

    def __init__(self, dev: 'PatchClamp', params):
        Thread.__init__(self, name=f"TestPulseThread({dev.name()})")
        self._clampDev = dev
        self._stop = False
        self._params = {
            'postProcessing': dev.testPulsePostProcessing,
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
            'vcAmplitude': -10e-3,
            'vcAverage': 4,
            'icPreDuration': 10e-3,
            'icPulseDuration': 80e-3,
            'icPostDuration': 80e-3,
            'icAmplitude': -10e-12,
            'icAverage': 4,
            '_index': 0,
        }
        self._lastTask = None

        self._daqName = self._clampDev.getDAQName("primary")
        self._clampName = self._clampDev.name()
        self._manager = getManager()

        self.setParameters(**params)

    def paramsForMode(self, mode: Literal['VC', 'IC', 'I=0']):
        taskParams = self._params.copy()
        taskParams['clampMode'] = mode
        if mode == 'I=0':
            test = 'ic'
        else:
            test = mode.lower()
        # select parameters to use based on clamp mode
        for k in self._params:
            # rename like icPulseDuration => pulseDuration
            if k[:2] == test:
                taskParams[k[2].lower() + k[3:]] = taskParams[k]
            # remove all ic__ and vc__ params
            if k[:2] in ('ic', 'vc'):
                taskParams.pop(k)
        return taskParams

    def setParameters(self, **kwds):
        newParams = self._params.copy()
        for k, v in kwds.items():
            if k not in self._params:
                raise KeyError(f"Unknown parameter {k}")
            newParams[k] = v
        newParams['_index'] += 1
        self._params = newParams

    def getParameter(self, param):
        return self._params[param]

    def start(self, **kwargs):
        self._stop = False
        Thread.start(self, **kwargs)

    def stop(self, block=False):
        self._stop = True
        if block and not self.wait(10000):
            raise RuntimeError("Timed out waiting for test pulse thread exit.")
                
    def run(self):
        while True:
            try:
                self.checkStop()
                start = ptime.time()
                self.runOnce(checkStop=True)

                interval = self._params['interval']
                if interval is None:
                    # start again immediately
                    continue
                
                # otherwise, wait until interval is over
                while True:
                    nextRun = start + self._params['interval']
                    now = ptime.time()
                    if now >= nextRun:
                        break
                    time.sleep(min(0.03, nextRun-now))
                    self.checkStop()
            except self.StopRequested:
                break
            except Exception:
                printExc("Error in test pulse thread (will try again):", msgType='warning')
                time.sleep(2.0)

    def runOnce(self, checkStop=False):
        currentMode = self._clampDev.getMode()
        params = self._params
        runMode = currentMode if params['clampMode'] is None else params['clampMode']

        # Can't reuse tasks yet; remove this when we can.
        self._lastTask = None

        if self._lastTask is None or self._lastTask._paramIndex != params['_index'] or self._lastTask._clampMode != runMode:
            taskParams = self.paramsForMode(runMode)
            task = self.createTask(taskParams)
            task._paramIndex = params['_index']
            task._clampMode = runMode
            self._lastTask = task
            self._lastTaskParams = taskParams
        else:
            task = self._lastTask

        # if clamp mode changed while we were fiddling around, then abort.
        task.reserveDevices()
        try:
            if self._clampDev.getMode() != currentMode:
                task.releaseDevices()
                return
            
            task.execute()
                
            while not task.isDone():
                if checkStop:
                    self.checkStop()
                time.sleep(0.01)
        
            tp = None
            if params['autoBiasEnabled']:
                # update bias before unlocking
                tp = self._makeTpResult(task)
                self.updateAutoBias(tp)
        finally:
            task.releaseDevices()

        if tp is None:
            # no auto bias, release before doing analysis
            tp = self._makeTpResult(task)

        self.sigTestPulseFinished.emit(self._clampDev, tp)

    def _makeTpResult(self, task: Task) -> PatchClampTestPulse:
        mode = task.command[self._clampName]['mode']
        params = self.paramsForMode(mode)
        result: MetaArray = task.getResult()[self._clampName]
        start_time = result.infoCopy()[2]['DAQ']['primary']['startTime']  # TODO what the shit is this
        pri = result['Channel': 'primary'].asarray()
        pulse_len = len(pri) // params['average']

        times = result.xvals('Time')  # starts at 0
        times = times[:pulse_len]

        pri = pri[:pulse_len * params['average']]
        pri = pri.reshape((params['average'], pulse_len)).mean(axis=0)
        pri = TSeries(
            channel_id='primary',
            data=pri,
            time_values=times,
            units='A' if mode == 'VC' else 'V',
            start_time=start_time,
        )

        cmd = task.command[self._clampName]['command']
        cmd = downsample(cmd[:pulse_len * params['downsample']], params['downsample'])
        holding = cmd[0]
        if mode == 'VC':
            extra_kwds = {
                'holding_potential': holding,
            }
        else:
            extra_kwds = {
                'holding_current': holding,
                'bridge_balance': getBridgeBalanceCompensation(result),
            }
        cmd -= holding  # neuroanalysis will double-count the baseline otherwise
        cmd = TSeries(
            channel_id='command',
            data=cmd,
            time_values=times,
            units='V' if mode == 'VC' else 'A',
            start_time=start_time,
        )

        rec = PatchClampRecording(
            channels={'primary': pri, 'command': cmd},
            clamp_mode=mode.lower(),
            device_type='patch clamp amplifier',
            device_id=self._clampName,
            start_time=start_time,
            **extra_kwds,
        )
        pri.recording = rec
        cmd.recording = rec

        tp = PatchClampTestPulse(rec)
        if self._params['postProcessing'] is not None:
            tp = self._params['postProcessing'](tp)
        return tp

    def createTask(self, params: dict) -> Task:
        duration = params['preDuration'] + params['pulseDuration'] + params['postDuration']
        numPts = int(float(duration * params['sampleRate']) * params['downsample']) // params['downsample']
        params['numPts'] = numPts  # send this back for analysis
        mode = params['clampMode']

        cmdData = np.empty(numPts * params['average'])
        cmdData[:] = self._clampDev.getHolding(mode)

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

        return self._manager.createTask(cmd)

    def checkStop(self):
        if self._stop:
            raise self.StopRequested()

    def updateAutoBias(self, tp: PatchClampTestPulse):
        analysis = tp.analysis
        mode = tp.clamp_mode
        if mode.upper() == 'VC':
            # set ic holding from baseline current, multiplied by some factor for a little more added safety.
            self._clampDev.setHolding('IC', analysis['baseline_current'] * self._params['autoBiasVCCarryover'])
        else:
            target = self._params['autoBiasTarget']
            if target is None:
                target = self._clampDev.getHolding("VC")

            rm = np.clip(analysis['steady_state_resistance'], 1e6, 10e9)
            vm = analysis['baseline_potential']

            dv = target - vm
            di = dv / rm

            holding = self._clampDev.getHolding(mode)
            newHolding = holding + di * self._params['autoBiasFollowRate']
            newHolding = np.clip(newHolding, self._params['autoBiasMinCurrent'], self._params['autoBiasMaxCurrent'])

            self._clampDev.setHolding(mode, newHolding)
