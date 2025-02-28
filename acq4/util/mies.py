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
        # self.igor.igor.sig_device_status_changed.connect(self.slot_device_status_changed) # will change for refactor
        self._initTPTime = None
        self._lastTPTime = None
        self._TPTimer = Qt.QTimer()
        self._TPTimer.setSingleShot(True)
        self._TPTimer.timeout.connect(self.getMIESUpdate)
        self.start()

    def start(self):
        self._exiting = False
        self.getMIESUpdate()

    # @Qt.Slot(str, str)
    # def slot_device_status_changed(self, device_name: str, device_tp_event):
    #     self.devices[device_name] = device_tp_event
    #     # potentionally can do more for this event

    def getMIESUpdate(self):
        future = self.igor("FFI_ReturnTPValues")
        future.add_done_callback(self._sigFutureComplete.emit)
        self._TPTimer.start(5000)  # by default recheck after 5 seconds, overridden if we get data

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

    def setManualPressure(self, pressure):
        return self.setCtrl("setvar_DataAcq_SSPressure", pressure)

    def setPressureSource(self, headstage: int, source: str, pressure=None):
        # if user, check user access & uncheck apply
        # if atmosphere, uncheck both
        # if regulator, check apply and uncheck user
        # button_DataAcq_SSSetPressureMan, check_DataACq_Pressure_User

        # use P_UpdatePressureMode(string device, variable pressureMode, string pressureControlName, variable checkALL)
        # with constants ...
        # Constant PRESSURE_METHOD_ATM      = -1
        # Constant PRESSURE_METHOD_MANUAL   = 4
        PRESSURE_METOD_ATM = -1
        PRESSURE_METHOD_MANUAL = 4
        # not sure yet on pressureControlName or checkAll (will check with Tim and update here)

        # update user mode check
        self.setCtrl("check_DataACq_Pressure_User", source == "user")

        if source == "user":
            return
        if source == "atmosphere":
            self.igor('DoPressureManual', 'ITC18USB_Dev_0', headstage, 0, 0).result()
            # self.igor('P_MethodAtmospheric', 'ITC18USB_Dev_0', headstage).result()
            # self.igor("P_UpdatePressureMode", self.getWindowName(), PRESSURE_METOD_ATM, "button_DataAcq_Approach", 0)
            # if self.manual_active:
            #     self.setCtrl("button_DataAcq_SSSetPressureMan", False)
            #     self.manual_active = False
        elif source == "regulator":
            self.igor('DoPressureManual', 'ITC18USB_Dev_0', headstage, 1, pressure).result()
            # self.igor('P_ManSetPressure', 'ITC18USB_Dev_0', headstage, 0).result()
            # self.igor("P_UpdatePressureMode", self.getWindowName(), PRESSURE_METHOD_MANUAL, "button_DataAcq_SSSetPressureMan", 0)
            # if not self.manual_active:
            #     self.setCtrl("button_DataAcq_SSSetPressureMan", True)
            #     self.manual_active = True
        else:
            raise ValueError(f"pressure source is not valid: {source}")

    def setApproach(self, hs):
        windowName = self.getWindowName()
        return self.igor("P_SetPressureMode", windowName, hs, PRESSURE_METHOD_APPROACH)

    def setSeal(self, hs):
        windowName = self.getWindowName()
        return self.igor("P_SetPressureMode", windowName, hs, PRESSURE_METHOD_SEAL)

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

    def getWindowName(self, ):
        if self._windowName is None:
            devices = self.getLockedDevices()
            for dev in devices:
                if dev != "":
                    print(f"setting windowName: {dev}")
                    self._windowName = devices[0]
            # if len(devices) > 0:
            #     self._windowName = devices[0]
        if self._windowName is None:
            print("DEBUG - Raising exception for windowName==None")
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