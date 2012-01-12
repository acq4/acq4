"""
GraphicsWidget displaying an image histogram along with gradient editor. Can be used to adjust the appearance of images.
"""


from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph.functions as fn
from GraphicsWidget import GraphicsWidget
from ViewBox import *
from GradientEditorItem import *
from LinearRegionItem import *
from PlotDataItem import *
from GridItem import *
import numpy as np

__all__ = ['HistogramLUTItem']


class HistogramLUTItem(GraphicsWidget):
    sigLookupTableChanged = QtCore.Signal(object)
    sigLevelsChanged = QtCore.Signal(object)
    
    def __init__(self, image=None):
        GraphicsWidget.__init__(self)
        self.layout = QtGui.QGraphicsGridLayout()
        self.setLayout(self.layout)
        self.vb = ViewBox()
        self.vb.setMaximumWidth(90)
        self.gradient = GradientEditorItem()
        self.gradient.setOrientation('right')
        self.gradient.loadPreset('grey')
        self.region = LinearRegionItem([0, 1], LinearRegionItem.Horizontal)
        self.vb.addItem(self.region)
        self.layout.addItem(self.vb, 0, 0)
        self.layout.addItem(self.gradient, 0, 1)
        self.range = None
        
        #self.grid = GridItem()
        #self.vb.addItem(self.grid)
        
        self.gradient.sigGradientChanged.connect(self.gradientChanged)
        self.region.sigRegionChanged.connect(self.regionChanged)
        self.plot = PlotDataItem()
        self.plot.rotate(90)
        self.vb.addItem(self.plot)
        
        self.imageItem = None
        if image is not None:
            self.setImageItem(image)
        #self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)

    #def sizeHint(self, *args):
        #return QtCore.QSizeF(115, 200)
        
    def setHistogramRange(self, mn, mx, padding=0.0):
        d = mx-mn
        mn -= d*padding
        mx += d*padding
        self.range = [mn,mx]
        self.updateRange()
        
    def autoHistogramRange(self):
        self.range = None
        self.updateRange()

    def setImageItem(self, img):
        self.imageItem = img
        img.sigImageChanged.connect(self.imageChanged)
        self.gradientChanged()
        self.regionChanged()
        self.imageChanged(autoLevel=True)
        self.vb.autoRange()
    
    def gradientChanged(self):
        if self.imageItem is not None:
            self.imageItem.setLookupTable(self.gradient.getLookupTable(512))
        self.sigLookupTableChanged.emit(self)

    def regionChanged(self):
        if self.imageItem is not None:
            self.imageItem.setLevels(self.region.getRegion())
        self.sigLevelsChanged.emit(self)

    def imageChanged(self, autoLevel=False):
        h = self.imageItem.getHistogram()
        if h[0] is None:
            return
        self.plot.setData(*h, fillLevel=0.0, brush=(100, 100, 200))
        if autoLevel:
            mn = h[0][int(len(h[0])*0.1)]
            mx = h[0][int(len(h[0])*0.9)]
            self.region.setRegion([mn, mx])
            self.updateRange()
            
    def updateRange(self):
        self.vb.autoRange()
        if self.range is not None:
            self.vb.setYRange(*self.range)
            
    def getLevels(self):
        return self.region.getRegion()
        
    def setLevels(self, mn, mx):
        self.region.setRegion([mn, mx])