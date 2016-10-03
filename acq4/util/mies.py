from igorpro import IgorThread
from PyQt4 import QtCore


def __reload__(old):
    MIES._bridge = old['MIESBridge']._bridge


class MIES(QtCore.QObject):
    """Bridge for communicating with MIES (multi-patch ephys and pressure control in IgorPro)
    """
    dataReady = QtCore.Signal()
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
        self._future = None
        self.windowName = 'ITC1600_Dev_0'
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.timeout.connect(self.getMIESUpdate)
        self.updateTimer.start(20)

    def getMIESUpdate(self):
        if self.usingZMQ:
            if self._future is None:
                self._future = self.igor("FFI_ReturnTPValues")
            if self._future.done():
                data = self._future.result()[...,0] # dimension hack when return value suddenly changed
                self._future = None
                self.processUpdate(data)
        else:
            raise RuntimeError("getMIESUpdate not supported in ActiveX")

    def processUpdate(self, data):
        if (self.currentData is None) or (data[0,0] > self.currentData[0,0]):
            self.currentData = data
            self.dataReady.emit()
        elif self.currentData is not None:
            # debugging an issue
            print data[:,0]
            print "{:f}".format(data[0,0])

    def getHeadstageData(self, hs, dataIndex=None):
        if self.currentData is None:
            return None, None
        else:
            ts = self.currentData[0,hs]
            if dataIndex is None:
                d = self.currentData[1:,hs]
            else:
                d = self.currentData[dataIndex,hs]
            return ts, d

    def resetData(self):
        self._future = None
        self.currentData = None

    def selectHeadstage(self, hs):
        return self.setCtrl("slider_DataAcq_ActiveHeadstage", hs)

    def setManualPressure(self, pressure):
        return self.setCtrl("setvar_DataAcq_SSPressure", pressure)

    def setApproach(self, hs):
        windowName = '"{}"'.format(self.windowName)
        return self.igor("P_MethodApproach", windowName, hs)
        #return self.setCtrl("button_DataAcq_Approach")

    def setSeal(self):
        windowName = '"{}"'.format(self.windowName)
        return self.igor("P_MethodSeal", windowName, hs)
        #return self.setCtrl("button_DataAcq_Seal")

    def setHeadstageActive(self, hs, active):
        return self.setCtrl('Check_DataAcqHS_%02d' % hs, active)

    def autoPipetteOffset(self):
        return self.setCtrl('button_DataAcq_AutoPipOffset_VC')

    def setCtrl(self, name, value=None):
        """Set or activate a GUI control in MIES.
        """
        windowName = '"{}"'.format(self.windowName)
        name_arg = '"{}"'.format(name)
        if value is None:
            return self.igor('PGC_SetAndActivateControl', windowName, name_arg)
        else:
            return self.igor('PGC_SetAndActivateControlVar', windowName, name_arg, value)


if __name__ == "__main__":
    from PyQt4 import QtGui
    import pyqtgraph as pg
    import sys

    class W(QtGui.QWidget):
        def __init__(self, parent=None):
            super(W, self).__init__(parent=parent)
            self.mies = MIES.getBridge(True)
            self.mies.dataReady.connect(self.grabit)
            self.b = QtGui.QPushButton("grab", parent=self)
            self.b.clicked.connect(self.mies.getMIESUpdate)
            l = QtGui.QVBoxLayout()
            l.addWidget(self.b)
            self.setLayout(l)

        def grabit(self):
            print self.mies.getHeadstageData(0)

    app = pg.mkQApp()
    w = W()
    w.show()
    sys.exit(app.exec_())