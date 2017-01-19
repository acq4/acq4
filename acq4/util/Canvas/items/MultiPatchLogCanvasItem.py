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
        


class MultiPatchLog(object):
    def __init__(self):
        self._devices = {}
        self._minTime = None
        self._maxTime = None

    def read(self, file):
        for line in open(file, 'r').readlines():
            fields = re.split(r',\s*', line.strip())
            time, device, eventType = fields[:3]
            data = fields[3:]
            time = float(time)
            if self._minTime is None:
                self._minTime = time
                self._maxTime = time
            else:
                self._minTime = min(self._minTime, time)
                self._maxTime = max(self._maxTime, time)

            event = {
                'event_time': time,
                'device': device,
                'event': eventType,
            }
            if eventType == 'move_stop':
                event['position'] = list(map(float, data))

            self._devices.setdefault(device, []).append(event)

        self.timeSlider.setMaximum(int(self._maxTime - self._minTime) + 1)

    def devices(self):
        return list(self._devices.keys())



class IrregularTimeSeries(object):
    """A sparsely-sampled time series.
    
    Allows efficient lookup of the series value at any time.
    """
    def __init__(self, interpolate=False):
        self.interpolate = interpolate
        self.events = []
        self.index = []  # each value maps a time in seconds to the index of the value recorded immediately after the time
    
    def append(self, time, value):
        i = int(time)

        # Extend index
        dif = i + 1 - len(self.index)
        if dif > 0:
            self.index.extend([len(self.events)] * dif)
        self.index[i] = len(self.events)
        
        self.events.append((float(time), value))
       
    def getValue(self, time):
        i = min(int(time), len(self.index)-1)
        j = self.index[i]
        while True:
            event = self.events[j]
            if event[0] <= time:
                break
            j -= 1
            if j < 0:
                return None
        
        if self.interpolate and j < len(self.events) - 1:
            t1, v1 = self.events[j]
            t2, v2 = self.events[j+1]
            s = (time - t1) / (t2 - t1)
            if isinstance(v1, tuple):
                return tuple([v1[k] * (1.0 - s) + v2[k] * s for k in range(len(v1))])
            else:
                return v1 * (1.0 - s) + v2 * s
            
        else:
            return event[1]
        return event
    
    def initialValue(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[0][1]
   
   
if __name__ == '__main__':
    d1 = IrregularTimeSeries(interpolate=True)
    
    d1.append(1, (1.1, 0))
    d1.append(3.9, (2.2, 10))
    d1.append(4, (3.3, 10))
    d1.append(4.1, (4.4, 10))
    d1.append(12, (5.5, 20))
    d1.append(20, (6.6, 30))
    
    d2 = IrregularTimeSeries(interpolate=False)
    
    d2.append(1, 'a')
    d2.append(4, 'b')
    d2.append(12, 'c')
    d2.append(20, 'd')
    
    for v in range(60):
        t = v / 2.0
        print("%0.1f:\t%s\t%s" % (t, d2.getValue(t), d1.getValue(t)))


