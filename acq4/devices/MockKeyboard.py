from acq4.devices.Keyboard import Keyboard


class MockKeyboard(Keyboard):
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
