from __future__ import print_function
from igorpro import IgorThread, IgorCallError
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
    def getBridge(cls, useZMQ=False):
        """Return a singleton MIESBridge instance.
        """
        # TODO: Handle switching between ZMQ and ActiveX?
        if cls._bridge is None:
            cls._bridge = MIES(useZMQ=useZMQ)
        return cls._bridge

    def __init__(self, useZMQ=False):
        super(MIES, self).__init__(parent=None)
        self.igor = IgorThread(useZMQ)
        self.usingZMQ = useZMQ
        self.currentData = None
        self._exiting = False
        self.windowName = 'ITC1600_Dev_0'
        self._sigFutureComplete.connect(self.processUpdate)
        self._initTPTime = None
        self._lastTPTime = None
        self._TPTimer = Qt.QTimer()
        self._TPTimer.setSingleShot(True)
        self._TPTimer.timeout.connect(self.getMIESUpdate)
        self.start()

    def start(self):
        self._exiting = False
        if self.usingZMQ:
            self.getMIESUpdate()

    def getMIESUpdate(self):
        if self.usingZMQ:
            future = self.igor("FFI_ReturnTPValues")
            future.add_done_callback(self._sigFutureComplete.emit)
            self._TPTimer.start(5000) # by default recheck after 5 seconds, overridden if we get data
        else:
            raise RuntimeError("getMIESUpdate not supported in ActiveX")

    def processUpdate(self, future):
        if not self._exiting:
            try:
                res = future.result()
                data = res[...,0] # dimension hack when return value suddenly changed
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
                self._initTPTime = TPArray[0,:][TPArray[0,:] > 0].min()
            except ValueError:
                pass
        self._lastTPTime = TPArray[0,:].max()

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

    def setApproach(self, hs):
        return self.igor("P_SetPressureMode", self.windowName, hs, PRESSURE_METHOD_APPROACH)

    def setSeal(self, hs):
        return self.igor("P_SetPressureMode", self.windowName, hs, PRESSURE_METHOD_SEAL)

    def setHeadstageActive(self, hs, active):
        return self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self):
        return self.setCtrl('button_DataAcq_AutoPipOffset_VC')

    def setCtrl(self, name, value=None):
        """Set or activate a GUI control in MIES."""
        name_arg = '"{}"'.format(name)
        if value is None:
            return self.igor('PGC_SetAndActivateControl', self.windowName, name)
        else:
            return self.igor('PGC_SetAndActivateControlVar', self.windowName, name, value)

    def quit(self):
        self._exiting = True


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