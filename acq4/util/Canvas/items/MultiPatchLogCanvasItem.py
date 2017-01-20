# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from CanvasItem import CanvasItem
import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np


class MultiPatchLogCanvasItem(CanvasItem):
    """For displaying events recorded in a MultiPatch log file.
    """
    def __init__(self, handle, **kwds):
        self.handle = handle
        self.data = handle.read()

        gitem = pg.ItemGroup()
        CanvasItem.__init__(self, gitem, **opts)
        
        self.ctrlWidget = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.ctrlWidget.setLayout(self.layout)
        self.timeSlider = QtGui.QSlider()
        self.layout.addWidget(self.timeSlider, 0, 0)

        self.timeSlider.valueChanged.connect(self.timeSliderChanged)

    def timeSliderChanged(self, v):
        pass

    @classmethod
    def checkFile(cls, fh):
        name = fh.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return 10
        else:
            return 0
        


