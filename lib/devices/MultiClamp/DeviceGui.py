# -*- coding: utf-8 -*-
from RackTemplate import *
from PyQt4 import QtCore, QtGui

class MCRackGui(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
    
