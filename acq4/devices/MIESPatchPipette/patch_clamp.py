from acq4.util.mies import MIES
from ..PatchClamp import PatchClamp
from ..PatchClamp.testpulse import TestPulseThread
from neuroanalysis.data import TSeries, PatchClampRecording
from neuroanalysis.test_pulse import PatchClampTestPulse
import numpy as np

import json

class MIESPatchClamp(PatchClamp):
    """PatchClamp device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge()
        self.mies.igor.sigMiesClampModeChanged.connect(self.miesClampModeChanged)
        self.mies.igor.sigMiesHoldingPotentialChanged.connect(self.miesHoldingPotentialChanged)
        self.mies.igor.sigMiesBiasCurrentChanged.connect(self.miesBiasCurrentChanged)
        self.mies.igor.sigMiesTestPulseStateChanged.connect(self.miesTestPulseStateChanged)
        PatchClamp.__init__(self, manager, config, name)
    
    def miesClampModeChanged(self, mode):
        s = {'mode': self.getMode(), 'holding': self.getHolding(mode=mode)}
        self.sigStateChanged.emit(s)
        self.sigHoldingChanged.emit(s['mode'], s['holding'])

    def miesHoldingPotentialChanged(self, value):
        s = {'mode': self.getMode(), 'holding': value}
        self.sigStateChanged.emit(s)
        self.sigHoldingChanged.emit(s['mode'], s['holding'])

    def miesBiasCurrentChanged(self, value):
        s = {'mode': self.getMode(), 'holding': value}
        self.sigStateChanged.emit(s)
        self.sigHoldingChanged.emit(s['mode'], s['holding'])

    def miesTestPulseStateChanged(self, enabled: bool):
        pass 

    def enableTestPulse(self, enable=True, block=False):
        result = self.mies.enableTestPulse(enable)
        if block:
            return result.result()

    def autoPipetteOffset(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.autoPipetteOffset()

    def setMode(self, mode):
        self.mies.setClampMode(self._headstage, mode)

    def getMode(self):
        return self.mies.getClampMode(self._headstage)

    def setHolding(self, mode=None, value=None):
        self.mies.setHolding(self._headstage, value)

    def getHolding(self, mode=None):
        return self.mies.getHolding(self._headstage, mode_override=mode)

    def getState(self):
        return {'mode': self.getMode()}
    
    def getLastState(self, mode=None):
        return {'holding': self.getHolding(mode)}
    
    def enableAutoBias(self, enable=True):
        self.setTestPulseParameters(autoBiasEnabled=enable)
        if self.autoBiasEnabled() != enable:
            self.mies.setAutoBias(self._headstage, enable)
            self.sigAutoBiasChanged.emit(self, enable, self.autoBiasTarget())

    def autoBiasEnabled(self):
        return self.mies.getAutoBias(self._headstage)
    
    def setAutoBiasTarget(self, target_value):
        current_value = self.autoBiasTarget()
        if current_value != target_value:
            self.mies.setAutoBiasTarget(self._headstage, target_value)
            enabled = self.autoBiasEnabled()
            self.sigAutoBiasChanged.emit(self, enabled, target_value)

    def autoBiasTarget(self):
        return self.mies.getAutoBiasTarget(self._headstage)
    
    def _initTestPulse(self, params):
        self.resetTestPulseHistory()
        self._testPulseThread = MIESTestPulseThread(self, params)
        self._testPulseThread.sigTestPulseFinished.connect(self._testPulseFinished)
        self._testPulseThread.started.connect(self.testPulseEnabledChanged)
        self._testPulseThread.finished.connect(self.testPulseEnabledChanged)
    
    def getDAQName(self, channel):
        return None
    
    def getParam(self, param):
        return None
    
    def deviceInterface(self, win):
        return None


class MIESTestPulseThread(TestPulseThread):
    def __init__(self, dev: PatchClamp, params):
        self.last_tp_raw = None
        self.last_tp_meta = None
        
        TestPulseThread.__init__(self, dev, params)
        self.mies = MIES.getBridge()
        self.mies.igor.sigTestPulseReady.connect(self.emitTestPulse)
        
    def emitTestPulse(self, message):
        tp_meta = json.loads(message[1].decode("utf-8"))
        if tp_meta['properties']['device'].startswith('DB_'):
            # ignore messages from data browser
            return
        self.last_tp_meta = tp_meta
        self.last_tp = np.frombuffer(message[2], dtype=np.float32)

        mode_list = ['VC', 'IC', 'I=0']
        mies_mode = tp_meta['properties']['clamp mode']
        mode = mode_list[mies_mode]

        holding = 0
        amplitude = 0

        extra_kwds = {}
        if mode == "VC":
            self.last_tp = self.last_tp / 1e12
            holding = tp_meta['amplifier']['HoldingPotential']['value'] / 1000
            amplitude = tp_meta['properties']['clamp amplitude']['value'] / 1000
            extra_kwds = {'holding_potential': holding,}
        elif mode == "IC":
            self.last_tp = self.last_tp / 1000
            holding = tp_meta['amplifier']['BiasCurrent']['value'] / 1e12
            amplitude = tp_meta['properties']['clamp amplitude']['value'] / 1e12
            extra_kwds = {
                'holding_current': holding,
                'bridge_balance': tp_meta['amplifier']['BridgeBalance']['value'] * 1e6
            }

        sample_period = tp_meta['properties']['sample interval DAC']['value'] / 1000 # units: ms (0.005)
        start_index = tp_meta['properties']['pulse start point DAC']['value'] # unit: 'point' (9000)
        stop_index = start_index + tp_meta['properties']['pulse duration DAC']['value'] # units: 'points' (2000)
        
        cmd = np.zeros(len(self.last_tp), dtype=np.float32)
        cmd[start_index:stop_index] = amplitude
        
        cmd = TSeries(
            channel_id='command',
            data=cmd,
            dt=sample_period, 
            units='V' if mode == 'VC' else 'A',
            start_time=tp_meta["properties"]['timestampUTC']['value'],
        )

        pri = TSeries(
            channel_id='primary',
            data=self.last_tp,
            dt=sample_period,  
            units='V' if mode == 'VC' else 'A',
            start_time=tp_meta["properties"]['timestampUTC']['value'],
        )

        rec = PatchClampRecording(
            channels={'primary': pri, 'command': cmd},
            clamp_mode=mode.lower(),
            device_type='patch clamp amplifier',
            device_id=self._clampName,
            start_time=tp_meta["properties"]['timestampUTC']['value'],
            **extra_kwds,
        )

        tp = PatchClampTestPulse(rec)

        self.sigTestPulseFinished.emit(self._clampDev, tp)