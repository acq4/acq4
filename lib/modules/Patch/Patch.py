# -*- coding: utf-8 -*-
from PatchTemplate import *
from PyQt4 import QtGui


class PatchWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QWidget()
        self.setCentralWidget(self.cw)
        self.ui = Ui_Form()
        self.ui.setupUi(self.cw)
        self.show()
        