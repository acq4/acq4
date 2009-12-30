# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from PlotWidget import *
from ImageView import *

class PlotWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        QtGui.QMainWindow.__init__(self)
        self.cw = PlotWidget()
        self.setCentralWidget(self.cw)
        for m in ['plot', 'autoRange']:
            setattr(self, m, getattr(self.cw, m))

class ImageWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        QtGui.QMainWindow.__init__(self)
        self.cw = ImageView()
        self.setCentralWidget(self.cw)
        for m in ['setImage', 'autoRange']:
            setattr(self, m, getattr(self.cw, m))

