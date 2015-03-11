from PyQt4 import QtGui, QtCore
from devicePagetemplate import *

class DevicePageWidget(QtGui.QWidget):
    def __init__(self, w):
        QtGui.QWidget.__init__(self)
        self.ui = Ui_Form()
        self.ui.setupUi(w)
