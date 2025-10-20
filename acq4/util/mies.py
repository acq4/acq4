import math
import time

from .igorpro import IgorBridge, IgorCallError
from acq4.util import Qt

# MIES constants, see MIES_Constants.ipf
PRESSURE_METHOD_APPROACH = 0
PRESSURE_METHOD_SEAL = 1


def __reload__(old):
    MIES._bridge = old['MIES']._bridge


class MIES(Qt.QObject):
    """Bridge for communicating with MIES (multi-patch ephys and pressure control in IgorPro)
    """
    sigDataReady = Qt.Signal(object)
    _sigFutureComplete = Qt.Signal(object)
    _bridge = None
    ALLDATA = None
    PEAKRES = 1
    SSRES = 2

    @classmethod
    def getBridge(cls):
        """Return a singleton MIESBridge instance.
        """
        if cls._bridge is None:
            cls._bridge = MIES()
        return cls._bridge

    def __init__(self):
        super(MIES, self).__init__(parent=None)
        self.igor = IgorBridge()
        self.currentData = None
        self.manual_active = False  # temporary fix for manual mode toggle button, see below
        self._exiting = False
        # self.windowName = 'ITC1600_Dev_0'
        self._windowName = None
        self.devices: list[str] = []
        self._sigFutureComplete.connect(self.processUpdate)
        self._initTPTime = None
        self._lastTPTime = None

    def processUpdate(self, future):
        if not self._exiting:
            try:
                res = future.result()
                data = res[..., 0]  # dimension hack when return value suddenly changed
                self.currentData = data
                self._updateTPTimes(data)
                self.sigDataReady.emit(data)
                nextCallWait = 2000
            except (IgorCallError, TypeError):
                # Test pulse isn't running, let's wait a little longer
                nextCallWait = 2000
            self._TPTimer.start(nextCallWait)

    def _updateTPTimes(self, TPArray):
        """Update globally tracked initial and end TP times"""
        if self._initTPTime is None:
            try:
                self._initTPTime = TPArray[0, :][TPArray[0, :] > 0].min()
            except ValueError:
                pass
        self._lastTPTime = TPArray[0, :].max()

    def getTPRange(self):
        if self._initTPTime is None:
            return 0, 0
        else:
            return self._initTPTime, self._lastTPTime

    def resetData(self):
        self.currentData = None

    def selectHeadstage(self, hs):
        if hs != 0:
            raise NotImplementedError("Multiple headstages not currently implemented")
        return
        # return self.setCtrl("slider_DataAcq_ActiveHeadstage", hs)
    
    def activateHeadstage(self, hs):
        return self.setCtrl(f"Check_DataAcqHS_0{hs}", True)
    
    def isHeadstageActive(self, hs):
        value = self.getCtrlValue(f'Check_DataAcqHS_0{hs}')
        return value == '1'

    def enableTestPulse(self, enable:bool):
        """Enable/disable test pulse for all active headstages"""
        return self.igor('FFI_TestpulseMD', self.getWindowName(), 1 if enable else 0)

    def getHolding(self, hs, mode):
        self.selectHeadstage(hs)
        if mode == "VC":
            val = float(self.getCtrlValue('setvar_DataAcq_Hold_VC')) / 1000
            enabled = self.getCtrlValue('check_DatAcq_HoldEnableVC') == '1'
        elif mode == "IC":
            val = float(self.getCtrlValue('setvar_DataAcq_Hold_IC')) / 1e12
            enabled = self.getCtrlValue('check_DatAcq_HoldEnable') == '1'
        return val, enabled
    
    def setHolding(self, headstage, mode, value):
        self.selectHeadstage(headstage)
        if mode == "VC":
            ret = self.setCtrl('setvar_DataAcq_Hold_VC', value * 1000)
            if value != 0:
                ret = self.setCtrl('check_DatAcq_HoldEnableVC', True)
        else:
            ret = self.setCtrl('setvar_DataAcq_Hold_IC', value * 1e12)
            if value != 0:
                ret = self.setCtrl('check_DatAcq_HoldEnable', True)
        return ret
    
    def setClampMode(self, hs: int, value: str): # IC | VC | I=0
        rtn_value = None
        if value == "VC":
            rtn_value = self.setCtrl(f'Radio_ClampMode_{hs*2}', True)
        elif value == "IC":
            rtn_value = self.setCtrl(f'Radio_ClampMode_{hs*2+1}', True)
        elif value.lower() == "i=0":
            rtn_value = self.setCtrl(f'Radio_ClampMode_{hs*2+1}IZ', True)

        return rtn_value

    def getClampMode(self, hs): # IC | VC | I=0
        clamp_mode = None
        is_active: str = self.getCtrlValue(f'Radio_ClampMode_{hs*2}') # due to wonky control naming
        if is_active == "1":
            clamp_mode = "VC"
        else:
            is_active: str = self.getCtrlValue(f'Radio_ClampMode_{hs*2+1}')
            if is_active == "1":
                clamp_mode = "IC"
            else:
                is_active: str = self.getCtrlValue(f'Radio_ClampMode_{hs*2+1}IZ')
                if is_active == "1":
                    clamp_mode = "I=0"
        return clamp_mode
    
    def setAutoBiasEnabled(self, headstage, value: bool):
        self.selectHeadstage(headstage)
        return self.setCtrl('check_DataAcq_AutoBias', value)
        
    def getAutoBiasEnabled(self, headstage):
        self.selectHeadstage(headstage)
        value = self.getCtrlValue('check_DataAcq_AutoBias')
        return True if value == "1" else False
        
    def setAutoBiasTarget(self, headstage, value):
        self.selectHeadstage(headstage)
        return self.setCtrl('setvar_DataAcq_AutoBiasV', value * 1000)
        
    def getAutoBiasTarget(self, headstage):
        self.selectHeadstage(headstage)
        return float(self.getCtrlValue('setvar_DataAcq_AutoBiasV')) / 1000
    
    def getManualPressure(self, headstage) -> float:
        self.selectHeadstage(headstage)
        return float(self.getCtrlValue('setvar_DataAcq_SSPressure'))
    
    def setPressureAndSource(self, headstage, source, pressure):
        if source == 'user':
            self.selectHeadstage(headstage)
            return self.setCtrl("check_DataACq_Pressure_User", True)
        try:
            source_val = {'atmosphere': 0, 'regulator': 1}[source]
        except KeyError:
            raise ValueError(f"Invalid pressure source '{source}'")
        return self.igor('DoPressureManual', self.getWindowName(), headstage, source_val, pressure)

    def setHeadstageActive(self, hs, active):
        return self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self, headstage):
        self.selectHeadstage(headstage)
        return self.setCtrl('button_DataAcq_AutoPipOffset_VC')

    def autoBridgeBalance(self, headstage):
        self.selectHeadstage(headstage)
        return self.setCtrl('button_DataAcq_AutoBridgeBal_IC')

    def autoCapComp(self, headstage):
        self.selectHeadstage(headstage)
        self.setCtrl('button_DataAcq_FastComp_VC')
        return self.setCtrl('button_DataAcq_SlowComp_VC')

    def getLockedDevices(self):
        res = self.igor("GetListOfLockedDevices").result()
        return res.split(";")

    def setCtrl(self, name, value=None):
        """Set or activate a GUI control in MIES."""
        windowName = self.getWindowName()
        if value is None:
            return self.igor('PGC_SetAndActivateControl', windowName, name)
        else:
            return self.igor('PGC_SetAndActivateControlVar', windowName, name, value)
        
    def getCtrlValue(self, mies_ctrl_name):
        windowName = self.getWindowName()
        return self.igor('GetGuiControlValue', windowName, mies_ctrl_name).result()

    def getWindowName(self, ):
        if self._windowName is None:
            devices = self.getLockedDevices()
            for dev in devices:
                if dev != "":
                    self._windowName = devices[0]
        if self._windowName is None:
            raise Exception("No device locked in IGOR")
        return self._windowName

    def quit(self):
        self._exiting = True
        self.igor.quit()


if __name__ == "__main__":
    from acq4.util import Qt
    import pyqtgraph as pg
    import sys


    class W(Qt.QWidget):
        def __init__(self, parent=None):
            super(W, self).__init__(parent=parent)
            self.mies = MIES.getBridge(True)
            self.mies.sigDataReady.connect(self.printit)
            self.b = Qt.QPushButton("stop", parent=self)
            self.b.clicked.connect(self.mies.quit)
            l = Qt.QVBoxLayout()
            l.addWidget(self.b)
            self.setLayout(l)

        def printit(self, data):
            print(data)


    app = pg.mkQApp()
    w = W()
    w.show()
    sys.exit(app.exec_())