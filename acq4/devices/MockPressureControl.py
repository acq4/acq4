from acq4.devices.PressureControl import PressureControl


class MockPressureControl(PressureControl):
    def _setPressure(self, p):
        self.pressure = p

    def getPressure(self):
        return getattr(self, "pressure", 10)

    def _setSource(self, source):
        self.source = source

    def getSource(self):
        return getattr(self, "source", self.sources[0])
