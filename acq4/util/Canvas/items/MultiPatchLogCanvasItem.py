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

        self.groupitem = pg.ItemGroup()

        self.pipettes = {}
        for dev in self.data.devices():
            arrow = pg.ArrowItem()
            self.pipettes[dev] = arrow
            arrow.setParentItem(self.groupitem)
        
        opts = {'movable': False, 'rotatable': False, 'name': self.handle.shortName()}
        opts.update(kwds)
        CanvasItem.__init__(self, self.groupitem, **opts)

        self.timeSlider = QtGui.QSlider()
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        self.timeSlider.setOrientation(QtCore.Qt.Horizontal)
        self.timeSlider.setMinimum(0)
        self.timeSlider.setMaximum(10 * (self.data.lastTime() - self.data.firstTime()))

        self.timeSlider.valueChanged.connect(self.timeSliderChanged)

    def timeSliderChanged(self, v):
        t = (v / 10.) + self.data.firstTime()
        pos = self.data.state(t)
        for dev,arrow in self.pipettes.items():
            p = pos.get(dev, {'position':None})['position']
            if p is None:
                arrow.hide()
            else:
                arrow.show()
                arrow.setPos(*p[:2])

    @classmethod
    def checkFile(cls, fh):
        name = fh.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return 10
        else:
            return 0

