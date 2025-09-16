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
        return self.setCtrl("slider_DataAcq_ActiveHeadstage", hs)
    
    def activateHeadstage(self, hs):
        return self.setCtrl(f"Check_DataAcqHS_0{hs}", True)
    
    def isHeadstageActive(self, hs):
        value = self.getCtrlValue(f'Check_DataAcqHS_0{hs}')
        return True if value == '1' else False

    def enableTestPulse(self, enable:bool):
        """Enable/disable test pulse for all active headstages"""
        return self.igor('API_TestPulse', self.getWindowName(), 1 if enable else 0)

    def getHolding(self, hs, mode_override=None):
        mode = ""
        if mode_override:
            mode = mode_override
        else:
            mode = self.getClampMode(hs)
        if mode == "VC":
            return int(self.getCtrlValue('setvar_DataAcq_Hold_VC')) / 1000
        elif mode == "IC":
            return int(self.getCtrlValue('setvar_DataAcq_Hold_IC')) / 1e12
    
    def setHolding(self, hs, value):
        mode: str = self.getClampMode(hs)
        if mode == "VC":
            return self.setCtrl('setvar_DataAcq_Hold_VC', value * 1000)
        elif mode == "IC":
            return self.setCtrl('setvar_DataAcq_Hold_IC', value * 1e12)
    
    def setClampMode(self, hs: int, value: str): # IC | VC | I=0
        rtn_value = None
        if value == "VC":
            rtn_value = self.setCtrl(f'Radio_ClampMode_{hs*2}', True)
        elif value == "IC":
            rtn_value = self.setCtrl(f'Radio_ClampMode_{hs*2+1}', True)
        elif value in ["I=0", "i=0"]:
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
    
    def setAutoBias(self, hs, value: bool):
        return self.setCtrl('check_DataAcq_AutoBias', value)
        
    def getAutoBias(self, hs):
        value = self.getCtrlValue('check_DataAcq_AutoBias')
        return True if value == "1" else False
        
    def setAutoBiasTarget(self, hs, value):
        return self.setCtrl('setvar_DataAcq_AutoBiasV', value * 1000)
        
    def getAutoBiasTarget(self, hs):
        return float(self.getCtrlValue('setvar_DataAcq_AutoBiasV')) / 1000
    
    def setManualPressure(self, pressure):
        # set pressure in MIES, then verify pressure is set in MIES
        # (necessary due to lag in MIES setting pressure)
        v = self.setCtrl("setvar_DataAcq_SSPressure", pressure)
        p = self.getManualPressure()
        if not math.isclose(pressure, p, abs_tol=0.0001):
            # test for x seconds
            found = False
            to = time.time() + 1 # one second timeout
            while not found and time.time() > to:
                p = self.getManualPressure()
                if math.isclose(pressure, p, abs_tol=0.0001):
                    found = True
            if not found:
                raise Exception("timeout while waiting for MIES pressure match")
        return v
    
    def getManualPressure(self) -> float:
        return float(self.getCtrlValue('setvar_DataAcq_SSPressure'))

    def setPressureSource(self, headstage: int, source: str, pressure=None):
        PRESSURE_METOD_ATM = -1
        PRESSURE_METHOD_MANUAL = 4

        self.setCtrl("check_DataACq_Pressure_User", source == "user")

        if source == "user":
            return
        if source == "atmosphere":
            self.igor('DoPressureManual', 'ITC18USB_Dev_0', headstage, 0, 0).result()
        elif source == "regulator":
            self.igor('DoPressureManual', 'ITC18USB_Dev_0', headstage, 1, pressure).result()
        else:
            raise ValueError(f"pressure source is not valid: {source}")

    # def setApproach(self, hs):
    #     windowName = self.getWindowName()
    #     return self.igor("P_SetPressureMode", windowName, hs, PRESSURE_METHOD_APPROACH)

    # def setSeal(self, hs):
    #     windowName = self.getWindowName()
    #     return self.igor("P_SetPressureMode", windowName, hs, PRESSURE_METHOD_SEAL)

    def setHeadstageActive(self, hs, active):
        return self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self):
        return self.setCtrl('button_DataAcq_AutoPipOffset_VC')

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