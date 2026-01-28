import time, queue, threading
import numpy as np
import pyqtgraph as pg
from acq4.util.mies import MIES
from ..PatchClamp import PatchClamp
from ..PatchClamp.testpulse import TestPulseThread
from neuroanalysis.data import TSeries, PatchClampRecording
from neuroanalysis.test_pulse import PatchClampTestPulse


class MIESPatchClamp(PatchClamp):
    """PatchClamp device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge()

        self._auto_bias_target_from_vc = False

        # grab initial stage values
        vc_holding, vc_holding_enable = self.mies.getHolding(self._headstage, 'VC')
        ic_holding, ic_holding_enable = self.mies.getHolding(self._headstage, 'IC')
        autobias_target = self.mies.getAutoBiasTarget(self._headstage)
        autobias_enable = self.mies.getAutoBiasEnabled(self._headstage)
        clamp_mode = self.mies.getClampMode(self._headstage)

        self._state = {
            'mode': clamp_mode,
            'HoldingPotential': vc_holding,
            'HoldingPotentialEnable': vc_holding_enable,
            'RSCompChaining': None,
            'Correction': None,
            'WholeCellCap': None,
            'RSCompChaining': None,
            'Correction': None,
            'PipetteOffsetVC': None,
            'BiasCurrent': ic_holding,
            'BiasCurrentEnable': ic_holding_enable,
            'AutoBiasVcom': autobias_target,
            'AutoBiasVcomVariance': None,
            'AutoBiasIbiasmax': None,
            'AutoBiasEnable': autobias_enable,
            'PipetteOffsetIC': None,
        }

        self.mies.igor.sigMiesClampModeChanged.connect(self.miesClampModeChanged)
        self.mies.igor.sigMiesClampStateChanged.connect(self.miesClampStateChanged)
        self.mies.igor.sigMiesTestPulseStateChanged.connect(self.miesTestPulseStateChanged)
        PatchClamp.__init__(self, manager, config, name)
    
    def miesClampModeChanged(self, headstage, mode):
        if headstage != self._headstage:
            return
        self._state['mode'] = mode
        self.sigStateChanged.emit(self._state)
        self.sigHoldingChanged.emit(mode, self.getHolding())

    def miesClampStateChanged(self, headstage, message):
        if headstage != self._headstage:
            return

        # Example messages:
        # {"HoldingPotential": {"unit": "mV", "value": 0.001}}
        # {"RSCompChaining": {"unit": "On/Off", "value": 0}}
        # {"Correction": {"unit": "%", "value": 0}}
        # {"WholeCellCap": {"unit": "pF", "value": 1e-12}}
        # {"RSCompChaining": {"unit": "On/Off", "value": 0}}
        # {"Correction": {"unit": "%", "value": 0}}
        # {"PipetteOffsetVC": {"unit": "mV", "value": 0}}
        # {"BiasCurrent": {"unit": "pA", "value": 1e-12}}
        # {"AutoBiasVcom": {"unit": "mV", "value": 0}}  # auto bias target voltage
        # {"AutoBiasVcomVariance": {"unit": "mV", "value": 1}}
        # {"AutoBiasIbiasmax": {"unit": "pA", "value": 200}}
        # {"AutoBiasEnable": {"unit": "On/Off", "value": 0}}
        # {"PipetteOffsetIC": {"unit": "mV", "value": 0}}

        for key, val in message.items():
            # print(f"MIESClampStateChanged: {key} -> {val}")
            if val['unit'] == 'On/Off':
                self._state[key] = bool(int(val['value']))
            elif val['unit'] == '%':
                self._state[key] = float(val['value'])
            else:
                # convert '-70.0 mV' -> -0.07 
                self._state[key] = pg.siEval(f"{val['value']} {val['unit']}")
            
            if key.startswith('HoldingPotential'):
                self.sigHoldingChanged.emit('VC', self.getHolding('VC'))
            elif key.startswith('BiasCurrent'):
                self.sigHoldingChanged.emit('IC', self.getHolding('IC'))

            if key in ['AutoBiasEnable', 'AutoBiasVcom']:
                self.sigAutoBiasChanged.emit(self, self._state['AutoBiasEnable'], self._state['AutoBiasVcom'])
        
        self.sigStateChanged.emit(self._state)

    def miesTestPulseStateChanged(self, enabled: bool):
        pass 

    def enableTestPulse(self, enable=True, block=False):
        result = self.mies.enableTestPulse(enable)
        if block:
            return result.result()

    def autoPipetteOffset(self):
        self.mies.autoPipetteOffset(self._headstage)

    def autoBridgeBalance(self):
        self.mies.autoBridgeBalance(self._headstage)

    def autoCapComp(self):
        self.mies.autoCapComp(self._headstage)

    def setMode(self, mode):
        self.mies.setClampMode(self._headstage, mode)

    def getMode(self):
        return self._state['mode']

    def setHolding(self, mode=None, value=None):
        self.mies.setHolding(self._headstage, mode, value)
        if mode == 'VC' and self._auto_bias_target_from_vc:
            self._updateAutoBiasTarget(value)

    def getHolding(self, mode=None):
        if mode is None:
            mode = self.getMode()

        state_key = {'V': 'HoldingPotential', 'I': 'BiasCurrent'}[mode[0]]
        enabled = self._state[state_key + 'Enable'] 
        return 0 if not enabled else self._state[state_key]

    def getState(self):
        return {'mode': self.getMode()}
    
    def getLastState(self, mode=None):
        return {'holding': self.getHolding(mode)}
    
    def enableAutoBias(self, enable=True):
        self.setTestPulseParameters(autoBiasEnabled=enable)
        if self.autoBiasEnabled() != enable:
            self.mies.setAutoBiasEnabled(self._headstage, enable)
            self.sigAutoBiasChanged.emit(self, enable, self.autoBiasTarget())

    def autoBiasEnabled(self):
        return self._state['AutoBiasEnable']
    
    def setAutoBiasTarget(self, target_value):
        """Set the auto bias target potential.

        If target_value is None, then this value is locked to the VC holding potential.
        """
        current_value = self.autoBiasTarget()
        self._auto_bias_target_from_vc = target_value is None

        if current_value != target_value:
            if target_value is None:
                target_value = self.getHolding('VC')
            self._updateAutoBiasTarget(target_value)
            enabled = self.autoBiasEnabled()
            self.sigAutoBiasChanged.emit(self, enabled, target_value)

    def _updateAutoBiasTarget(self, target):
        return self.mies.setAutoBiasTarget(self._headstage, target)

    def autoBiasTarget(self):
        if self._auto_bias_target_from_vc:
            return None
        return self._state['AutoBiasVcom']
    
    def _initTestPulse(self, params):
        self.resetTestPulseHistory()
        self._testPulseThread = MIESTestPulseThread(self, params)
        self._testPulseThread.sigTestPulseAnalyzed.connect(self._testPulseFinished)
        self._testPulseThread.started.connect(self.testPulseEnabledChanged)
        self._testPulseThread.finished.connect(self.testPulseEnabledChanged)
    
    def getDAQName(self, channel):
        return None
    
    def getParam(self, param):
        return None
    
    def deviceInterface(self, win):
        return None


class MIESTestPulseThread(TestPulseThread):
    """
    TestPulseThread is for acquiring and analyzing test pulses in the background.
    MIESTestPulseThread does only the analysis; MIES does the acquisition and sends data here.
    """
    def __init__(self, dev: MIESPatchClamp, params):
        self.last_tp_raw = None
        self.last_tp_meta = None
        
        self.tp_queue = queue.Queue()

        # technically this chass is already subclasses from Thread, but
        # in the suberclass this is used in a very different way, and I son't want to risk
        # any strange collisions here
        self.analysis_thread = threading.Thread(target=self.process_pulses, daemon=True)

        TestPulseThread.__init__(self, dev, params)
        self.mies = MIES.getBridge()
        self.mies.igor.sigTestPulseReady.connect(self.test_pulse_received)

        self.analysis_thread.start()
        
    def test_pulse_received(self, tp_meta, data_buffer):
        self.tp_queue.put((tp_meta, data_buffer))

    def process_pulses(self):
        """In background thread: receive data from MIES, convert, analyze, and emit."""
        last_error_time = 0
        while True:
            try:
                next_tp_data = self.tp_queue.get()
                tp = self.make_test_pulse(*next_tp_data)
                if tp is None:
                    continue
                tp.analysis  # run and cache analysis results
                self.sigTestPulseAnalyzed.emit(self._clampDev, tp)
            except Exception as exc:
                now = time.time()
                if now - last_error_time > 3:
                    print(f"Error in MIESTestPulseThread: {exc}")
                    last_error_time = now

    def make_test_pulse(self, tp_meta, data_buffer):
        """Create a PatchClampTestPulse instance from MIES test pulse data
        """
        # Example tp_meta:
        # {
        #     'amplifier': {
        #         'AutoBiasEnable': {'unit': 'On/Off', 'value': 0}, 
        #         'AutoBiasIbiasmax': {'unit': 'pA', 'value': 200}, 
        #         'AutoBiasVcom': {'unit': 'mV', 'value': 0}, 
        #         'AutoBiasVcomVariance': {'unit': 'mV', 'value': 1}, 
        #         'BiasCurrent': {'unit': 'pA', 'value': 1}, 
        #         'BiasCurrentEnable': {'unit': 'On/Off', 'value': 0}, 
        #         'BridgeBalance': {'unit': 'MΩ', 'value': 0}, 
        #         'BridgeBalanceEnable': {'unit': 'On/Off', 'value': 0}, 
        #         'CapNeut': {'unit': 'pF', 'value': 0}, 
        #         'CapNeutEnable': {'unit': 'On/Off', 'value': 0}, 
        #         'PipetteOffsetIC': {'unit': 'mV', 'value': 0}
        #     }, 
        #     'properties': {
        #         'baseline fraction': {'unit': '%', 'value': 45}, 
        #         'clamp amplitude': {'unit': 'pA', 'value': 50}, 
        #         'clamp mode': 1, 
        #         'device': 'ITC18USB_Dev_0', 
        #         'headstage': 0, 
        #         'pulse duration ADC': {'unit': 'points', 'value': 2000}, 
        #         'pulse duration DAC': {'unit': 'points', 'value': 2000}, 
        #         'pulse start point ADC': {'unit': 'point', 'value': 9000}, 
        #         'pulse start point DAC': {'unit': 'point', 'value': 9000}, 
        #         'sample interval ADC': {'unit': 'ms', 'value': 0.005}, 
        #         'sample interval DAC': {'unit': 'ms', 'value': 0.005}, 
        #         'timestamp': {'unit': 's', 'value': 3843808306.022667}, 
        #         'timestampUTC': {'unit': 's', 'value': 3843833506.022667}, 
        #         'tp cycle id': 662833, 
        #         'tp length ADC': {'unit': 'points', 'value': 20000}, 
        #         'tp length DAC': {'unit': 'points', 'value': 20000}, 
        #         'tp marker': 1471556619
        #     }, 
        #     'results': {
        #         'average baseline steady state': {'unit': 'mV', 'value': 1023.96875}, 
        #         'average tp steady state': {'unit': 'mV', 'value': 1023.96875}, 
        #         'instantaneous': {'unit': 'mV', 'value': 1023.96875}, 
        #         'instantaneous resistance': {'unit': 'MΩ', 'value': 0}, 
        #         'steady state resistance': {'unit': 'MΩ', 'value': 0}
        #     }
        # }

        if tp_meta['properties']['device'] != self.mies.getWindowName():
            # ignore messages from data browser
            return
        if tp_meta['properties']['headstage'] != self._clampDev._headstage:
            # ignore messages from other headstages
            return
        
        self.last_tp_meta = tp_meta
        self.last_tp = np.frombuffer(data_buffer, dtype=np.float32)

        mies_mode = tp_meta['properties']['clamp mode']
        mode = ['VC', 'IC', 'I=0'][mies_mode]

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

        return PatchClampTestPulse(rec)
