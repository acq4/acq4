from __future__ import print_function
from acq4.util import Qt
from .devicePagetemplate import *

class DevicePageWidget(Qt.QWidget):
    def __init__(self, w):
        Qt.QWidget.__init__(self)
        self.ui = Ui_Form()
        self.ui.setupUi(w)
