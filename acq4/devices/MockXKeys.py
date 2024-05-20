from acq4.devices.BaseXKeys import BaseXKeys


class MockXKeys(BaseXKeys):
    def setBacklights(self, state, **kwds):
        pass

    def getBacklights(self):
        pass

    def setBacklight(self, key, blue=None, red=None):
        pass

    def getState(self):
        pass

    def capabilities(self):
        pass

    def quit(self):
        pass
