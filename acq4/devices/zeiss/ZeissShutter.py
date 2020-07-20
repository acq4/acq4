class ZeissRLShutter(Device):
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(Qt.QMutex.Recursive)

        self.zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        self.mtbRoot = self.zeiss.connect()
        self.m_shutter = self.zeiss.getShutter()
        self.zeiss.getShutter().registerEventHandlers(self.shutterStateChanged, self.shutterStateSettled)
        self.zeiss.getShutter().registerRLShutterEvents(self.rlShutterStateChanged)

    def shutterStateChanged(self, position):
        pass

    def shutterStateSettled(self, position):
        self.sigSwitchChanged.emit(self, position)

    def rlShutterStateChanged(self, position):
        pass

    def setRLShutter(self, state):
        self.m_shutter.setRLShutter(state)

    def getRLShutter(self):
        return self.m_shutter.getRLShutter()

    def disconnect(self):
        self.zeiss.disconnect()
