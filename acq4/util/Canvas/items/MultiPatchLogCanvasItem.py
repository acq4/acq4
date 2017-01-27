# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from CanvasItem import CanvasItem
import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np
from .MarkersItem import MarkersItem


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
        
        opts = {'movable': False, 'rotatable': False}
        opts.update(kwds)
        if opts.get('name') is None:
            opts['name'] = self.handle.shortName()            
        CanvasItem.__init__(self, self.groupitem, **opts)

        self.timeSlider = QtGui.QSlider()
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        self._timeSliderResolution = 10.  # 10 ticks per second on the time slider
        self.timeSlider.setOrientation(QtCore.Qt.Horizontal)
        self.timeSlider.setMinimum(0)
        self.timeSlider.setMaximum(self._timeSliderResolution * (self.data.lastTime() - self.data.firstTime()))
        self.timeSlider.valueChanged.connect(self.timeSliderChanged)

        self.createMarkersBtn = QtGui.QPushButton('Create markers')
        self.layout.addWidget(self.createMarkersBtn, self.layout.rowCount(), 0)
        self.createMarkersBtn.clicked.connect(self.createMarkersClicked)

    def timeSliderChanged(self, v):
        t = self.currentTime()
        pos = self.data.state(t)
        for dev,arrow in self.pipettes.items():
            p = pos.get(dev, {'position':None})['position']
            if p is None:
                arrow.hide()
            else:
                arrow.show()
                arrow.setPos(*p[:2])

    def currentTime(self):
        v = self.timeSlider.value()
        return (v / self._timeSliderResolution) + self.data.firstTime()

    def setCurrentTime(self, t):
        self.timeSlider.setValue(self._timeSliderResolution * (t - self.data.firstTime()))

    def createMarkersClicked(self):
        markers = MarkersItem(name=self.name + '_markers')
        state = self.data.state(self.currentTime())
        for k,v in state.items():
            if v.get('position') is None:
                continue
            markers.addMarker(name=k, position=v['position'])
        self.canvas.addItem(markers)

    @classmethod
    def checkFile(cls, fh):
        name = fh.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return 10
        else:
            return 0

    def saveState(self, **kwds):
        state = CanvasItem.saveState(self, **kwds)
        state['currentTime'] = self.currentTime()
        return state

    def restoreState(self, state):
        self.setCurrentTime(state.pop('currentTime'))
        CanvasItem.restoreState(self, state)
