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
import numpy as np

__all__ = ['HistogramLUTItem']


class HistogramLUTItem(GraphicsWidget):
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

    def regionChanged(self):
        if self.imageItem is not None:
            self.imageItem.setLevels(self.region.getRegion())

    def imageChanged(self, autoLevel=False):
        h = self.imageItem.getHistogram()
        self.plot.setData(*h, fillLevel=0.0, brush=(100, 100, 200))
        if autoLevel:
            mn = h[0][int(len(h[0])*0.1)]
            mx = h[0][int(len(h[0])*0.9)]
            self.region.setRegion([mn, mx])
            
        