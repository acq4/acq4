import numpy as np
from typing import Literal

from acq4.devices.Device import Device
from acq4.devices.PatchClamp.gui import PatchClampDeviceGui
from acq4.devices.PatchClamp.testpulse import TestPulseThread
from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import Qt
from neuroanalysis.test_pulse import PatchClampTestPulse


class PatchClamp(Device):
    """Base class for all patch clamp amplifier devices.
    
    Signals
    -------
    sigStateChanged(state)
        Emitted when any state parameters have changed
    sigHoldingChanged(self, clamp_mode)
        Emitted when the holding value for any clamp mode has changed
    """

    sigStateChanged = Qt.Signal(object)  # state
    sigHoldingChanged = Qt.Signal(object, object)  # mode, value
    sigTestPulseFinished = Qt.Signal(object, object)  # self, TestPulse
    sigTestPulseEnabled = Qt.Signal(object, object)  # self, enabled
    sigAutoBiasChanged = Qt.Signal(object, object, object)  # self, enabled, target

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        self.config = config
        self._lastTestPulse = None
        self._testPulseThread = None
        self._initTestPulse(config.get('testPulse', {}))
        self._testPulseHistorySize = 0
        self._testPulseHistory = None
        self._testPulseAnalysisOverrides = {}

    def deviceInterface(self, win):
        return PatchClampDeviceGui(self, win)

    def description(self) -> str:
        return str(type(self))

    def getState(self):
        """Return a dictionary of active state parameters
        """
        raise NotImplementedError()

    def getLastState(self, mode=None):
        """Return the state when last in the given mode"""
        raise NotImplementedError()

    def getParam(self, param):
        """Return the value of a single state parameter
        """
        raise NotImplementedError()

    def setParam(self, param, value):
        """Set the value of a single state parameter
        """
        raise NotImplementedError()

    def getHolding(self, mode=None):
        """Return the holding value for a specific clamp mode.
        
        If no clamp mode is given, then return the holding value for the currently active clamp mode.
        """
        raise NotImplementedError()

    def setHolding(self, mode=None, value=None):
        """Set the holding value for a specific clamp mode.
        """
        raise NotImplementedError()

    def mockTestPulseAnalysis(self, **values):
        self._testPulseAnalysisOverrides.update(values)

    def disableMockTestPulseAnalysis(self):
        self._testPulseAnalysisOverrides = {}

    def testPulsePostProcessing(self, tp: PatchClampTestPulse):
        """Perform extra modifications to the test pulse, e.g. manually override its analysis."""
        if self._testPulseAnalysisOverrides:
            tp.analysis.update(self._testPulseAnalysisOverrides)
        return tp

    def autoPipetteOffset(self):
        """Automatically set the pipette offset.
        """
        raise NotImplementedError()

    def autoBridgeBalance(self):
        """Automatically set the bridge balance.
        """
        raise NotImplementedError()

    def autoCapComp(self):
        """Automatically configure capacitance compensation.
        """
        raise NotImplementedError()

    def getMode(self) -> Literal['VC', 'IC', 'I=0']:
        """Get the currently active clamp mode ('IC', 'VC', etc.)
        """
        raise NotImplementedError()

    def setMode(self, mode: Literal['VC', 'IC', 'I=0']):
        """Set the currently active clamp mode ('IC', 'VC', etc.)
        """
        raise NotImplementedError()

    def getDAQName(self, channel):
        """Return the name of the DAQ device that performs digitization for this amplifier channel.
        """
        raise NotImplementedError()

    def _initTestPulse(self, params):
        self.resetTestPulseHistory()
        self._testPulseThread = TestPulseThread(self, params)
        self._testPulseThread.sigTestPulseFinished.connect(self._testPulseFinished)
        self._testPulseThread.started.connect(self.testPulseEnabledChanged)
        self._testPulseThread.finished.connect(self.testPulseEnabledChanged)

    def _testPulseFinished(self, dev, result: PatchClampTestPulse):
        self._lastTestPulse = result
        if self._testPulseHistorySize >= self._testPulseHistory.shape[0]:
            newTPH = np.empty(self._testPulseHistory.shape[0] * 2, dtype=self._testPulseHistory.dtype)
            newTPH[:self._testPulseHistory.shape[0]] = self._testPulseHistory
            self._testPulseHistory = newTPH
        analysis = result.analysis
        self._testPulseHistory[self._testPulseHistorySize]['event_time'] = result.start_time
        for k in analysis:
            val = analysis[k]
            if val is None:
                val = np.nan
            self._testPulseHistory[self._testPulseHistorySize][k] = val
        self._testPulseHistorySize += 1

        self.sigTestPulseFinished.emit(self, result)

    def testPulseHistory(self):
        return self._testPulseHistory[:self._testPulseHistorySize].copy()

    def resetTestPulseHistory(self):
        self._lastTestPulse = None
        self._testPulseHistory = np.empty(1000, dtype=TEST_PULSE_NUMPY_DTYPE)

        self._testPulseHistorySize = 0

    def enableTestPulse(self, enable=True, block=False):
        if enable:
            self._testPulseThread.start()
        elif self._testPulseThread is not None:
            self._testPulseThread.stop(block=block)

    def testPulseEnabled(self):
        return self._testPulseThread.isRunning()

    def testPulseEnabledChanged(self):
        self.sigTestPulseEnabled.emit(self, self.testPulseEnabled())

    def setTestPulseParameters(self, **params):
        self._testPulseThread.setParameters(**params)

    def lastTestPulse(self):
        return self._lastTestPulse

    def enableAutoBias(self, enable=True):
        self.setTestPulseParameters(autoBiasEnabled=enable)
        self.sigAutoBiasChanged.emit(self, enable, self.autoBiasTarget())

    def autoBiasEnabled(self):
        return self._testPulseThread.getParameter('autoBiasEnabled')

    def setAutoBiasTarget(self, v):
        self.setTestPulseParameters(autoBiasTarget=v)
        enabled = self.autoBiasEnabled()
        self.sigAutoBiasChanged.emit(self, enabled, v)

    def autoBiasTarget(self):
        return self._testPulseThread.getParameter('autoBiasTarget')
