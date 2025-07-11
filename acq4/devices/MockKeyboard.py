import numpy as np

from acq4.devices.Keyboard import Keyboard
from acq4.util import Qt


class MockKeyboard(Keyboard):
    """
    Simulated keyboard device for testing and demonstration.
    
    Provides the same interface as real programmable keyboards but without hardware.
    Creates a GUI with clickable buttons for registered key callbacks.
    
    Configuration options:
    
    No device-specific configuration options. Key callbacks are registered 
    programmatically via addKeyCallback() method.
    
    Example configuration::
    
        MockKeyboard:
            driver: 'MockKeyboard'
    """
    def setBacklights(self, state, **kwds):
        pass

    def getBacklights(self):
        return np.zeros((100, 100, 2), dtype='ubyte')

    def setBacklight(self, key, blue=None, red=None):
        pass

    def setIntensity(self, b1, b2):
        pass

    def getState(self):
        pass

    def capabilities(self):
        pass

    def quit(self):
        pass

    def deviceInterface(self, win):
        return MockKeyboardInterface(self, win)


class MockKeyboardInterface(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.dev.sigCallbacksChanged.connect(self.updateButtons)
        self.win = win
        self.layout = Qt.QGridLayout(self)
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self._buttons = {}

        self.updateButtons(dev)

    def updateButtons(self, dev):
        for btn in self._buttons.values():
            btn.deleteLater()
        keys = dev._callbacks.keys()
        for i, key in enumerate(keys):
            btn = Qt.QPushButton(str(key), self)
            btn.setCheckable(True)
            btn.clicked.connect(self.keyClicked)
            self.layout.addWidget(btn, i // 4, i % 4)
            self._buttons[key] = btn

    def keyClicked(self):
        btn = self.sender()
        key = eval(btn.text())
        if btn.isChecked():
            self.dev.sigStateChanged.emit(self.dev, {'keys': [(key, True)]})
        else:
            self.dev.sigStateChanged.emit(self.dev, {'keys': [(key, False)]})