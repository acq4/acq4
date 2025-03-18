#!/usr/bin/env python
"""
Simple test script for the Sonicator device and GUI.
"""

import sys
import pyqtgraph as pg
from PyQt5 import QtWidgets

from acq4.devices.MockSonicator import MockSonicator

class TestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonicator Test")
        self.resize(600, 500)
        
        # Create a mock sonicator device
        self.sonicator = MockSonicator(name="test_sonicator")
        
        # Create and set the GUI as central widget
        self.gui = self.sonicator.deviceInterface(self)
        self.setCentralWidget(self.gui)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())
