from __future__ import print_function
from acq4.util import Qt

Ui_Form = Qt.importTemplate('.devicePagetemplate')


class DevicePageWidget(Qt.QWidget):
    def __init__(self, w):
        Qt.QWidget.__init__(self)
        self.ui = Ui_Form()
        self.ui.setupUi(w)
