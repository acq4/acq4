# -*- coding: utf-8 -*-
from numpy import ndarray
from graphicsItems import *
from PlotItem import *

try:
    from metaarray import *
    HAVE_METAARRAY = True
except:
    HAVE_METAARRAY = False
    
    
class MultiPlotItem(QtGui.QGraphicsWidget):
    def __init__(self, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.layout = QtGui.QGraphicsGridLayout()
        self.layout.setContentsMargins(1,1,1,1)
        self.setLayout(self.layout)
        self.layout.setHorizontalSpacing(0)
        self.layout.setVerticalSpacing(4)
        self.plots = []

    def plot(self, data):
        #self.layout.clear()
        self.plots = []
            
        if HAVE_METAARRAY and isinstance(data, MetaArray):
            if data.ndim != 2:
                raise Exception("MultiPlot currently only accepts 2D MetaArray.")
            ic = data.infoCopy()
            ax = 0
            for i in [0, 1]:
                if 'cols' in ic[i]:
                    ax = i
                    break
                    
            for i in range(data.shape[ax]):
                pi = PlotItem()
                sl = [slice(None)] * 2
                sl[ax] = i
                pi.plot(data[tuple(sl)])
                self.layout.addItem(pi, i, 0)
                self.plots.append((pi, i, 0))
                
        else:
            raise Exception("Data type %s not supported for MultiPlot." % type(data))
            
        