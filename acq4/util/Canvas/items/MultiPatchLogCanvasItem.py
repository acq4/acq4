# -*- coding: utf-8 -*-
from __future__ import print_function
import time, re
from acq4.util import Qt
from .CanvasItem import CanvasItem
import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np
from .MarkersCanvasItem import MarkersCanvasItem
from .itemtypes import registerItemType


class MultiPatchLogCanvasItem(CanvasItem):
    """For displaying events recorded in a MultiPatch log file.
    """
    _typeName = "Multipatch Log"
    
    def __init__(self, handle, **kwds):
        kwds.pop('viewRect', None)
        
        self.data = handle.read()
        self.groupitem = pg.ItemGroup()

        self.pipettes = {}
        for dev in self.data.devices():
            arrow = pg.ArrowItem()
            self.pipettes[dev] = arrow
            arrow.setParentItem(self.groupitem)
        
        opts = {'movable': False, 'rotatable': False, 'handle': handle}
        opts.update(kwds)
        if opts.get('name') is None:
            opts['name'] = handle.shortName()            
        CanvasItem.__init__(self, self.groupitem, **opts)

        self._timeSliderResolution = 10.  # 10 ticks per second on the time slider
        self._mpCtrlWidget = MultiPatchLogCtrlWidget()
        self.layout.addWidget(self._mpCtrlWidget, self.layout.rowCount(), 0, 1, 2)
        self._mpCtrlWidget.timeSlider.setMaximum(self._timeSliderResolution * (self.data.lastTime() - self.data.firstTime()))
        self._mpCtrlWidget.timeSlider.valueChanged.connect(self.timeSliderChanged)
        self._mpCtrlWidget.createMarkersBtn.clicked.connect(self.createMarkersClicked)
        
        self.timeSliderChanged(0)

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
        if t < 1e7:
            # looks like a relative time
            h = int(t / 3600.)
            m = int((t % 3600) / 60.)
            s = t % 60
            tstr = "%d:%02d:%0.1f" % (h, m, s)
        else:
            # looks like a timestamp
            tt = time.localtime(t)
            tstr = time.strftime("%Y-%m-%d %H:%M:%S", tt)
        self._mpCtrlWidget.timeLabel.setText(tstr)

    def currentTime(self):
        v = self._mpCtrlWidget.timeSlider.value()
        return (v / self._timeSliderResolution) + self.data.firstTime()

    def setCurrentTime(self, t):
        self._mpCtrlWidget.timeSlider.setValue(self._timeSliderResolution * (t - self.data.firstTime()))

    def createMarkersClicked(self):
        fmt = str(self._mpCtrlWidget.createMarkersFormat.text())

        # get name and position of each new marker
        state = self.data.state(self.currentTime())
        pips = []
        for k,v in state.items():
            if v.get('position') is None:
                continue
            
            # Extract marker number from pipette name
            m = re.match(r'\D+(\d+)', k)
            if m is not None:
                n = int(m.group(1))
                name = fmt % n
            else:
                name = k
            
            pips.append((name, v['position']))
        pips.sort()

        # create new canvas item and add markers
        markers = MarkersCanvasItem(name=self.name + '_markers')
        for name, pos in pips:
            markers.addMarker(name=name, position=pos)
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

registerItemType(MultiPatchLogCanvasItem)



class MultiPatchLogCtrlWidget(Qt.QWidget):
    def __init__(self):
        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.timeSlider = Qt.QSlider()
        self.layout.addWidget(self.timeSlider, 0, 0)
        self.timeSlider.setOrientation(Qt.Qt.Horizontal)
        self.timeSlider.setMinimum(0)

        self.timeLabel = Qt.QLabel()
        self.layout.addWidget(self.timeLabel, 0, 1)

        self.createMarkersBtn = Qt.QPushButton('Create markers')
        self.layout.addWidget(self.createMarkersBtn, 1, 0)
        
        self.createMarkersFormat = Qt.QLineEdit("Cell_%02d")
        self.layout.addWidget(self.createMarkersFormat, 1, 1)
