"""
GraphicsWidget displaying an image histogram along with gradient editor. Can be used to adjust the appearance of images.
"""


from ..Qt import QtGui, QtCore
from .. import functions as fn
from .GraphicsWidget import GraphicsWidget
from .ViewBox import *
from .GradientEditorItem import *
from .LinearRegionItem import *
from .PlotDataItem import *
from .AxisItem import *
from .GridItem import *
from ..Point import Point
from .. import functions as fn
import numpy as np
from .. import debug as debug

import weakref

__all__ = ['HistogramLUTItem']


class HistogramLUTItem(GraphicsWidget):
    """
    This is a graphicsWidget which provides controls for adjusting the display of an image.
    Includes:

    - Image histogram 
    - Movable region over histogram to select black/white levels
    - Gradient editor to define color lookup table for single-channel images
    """
    
    sigLookupTableChanged = QtCore.Signal(object)
    sigLevelsChanged = QtCore.Signal(object)
    sigLevelChangeFinished = QtCore.Signal(object)
    
    def __init__(self, image=None, fillHistogram=True, rgbHistogram=False, levelMode='mono'):
        """
        If *image* (ImageItem) is provided, then the control will be automatically linked to the image and changes to the control will be immediately reflected in the image's appearance.
        By default, the histogram is rendered with a fill. For performance, set *fillHistogram* = False.
        """
        GraphicsWidget.__init__(self)
        self.lut = None
        self.imageItem = lambda: None  # fake a dead weakref
        self.levelMode = levelMode
        self.rgbHistogram = rgbHistogram
        
        self.layout = QtGui.QGraphicsGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(1,1,1,1)
        self.layout.setSpacing(0)
        self.vb = ViewBox()
        self.vb.setBackgroundColor(0.3)
        self.vb.setMaximumWidth(152)
        self.vb.setMinimumWidth(45)
        self.vb.setMouseEnabled(x=False, y=True)
        item = PlotDataItem(x=np.linspace(0, 1, 10), y=[1,4,2,3,7,4,6,5,8,7])
        self.vb.addItem(item)
        self.gradient = GradientEditorItem()
        self.gradient.setOrientation('right')
        self.gradient.loadPreset('grey')
        self.regions = [
            LinearRegionItem([0, 1], 'horizontal', swapMode='block'),
            LinearRegionItem([0, 1], 'horizontal', swapMode='block', pen='r',
                             brush=fn.mkBrush((255, 0, 0, 50)), span=(0., 1/3.)),
            LinearRegionItem([0, 1], 'horizontal', swapMode='block', pen='g',
                             brush=fn.mkBrush((0, 255, 0, 50)), span=(1/3., 2/3.)),
            LinearRegionItem([0, 1], 'horizontal', swapMode='block', pen='b',
                             brush=fn.mkBrush((0, 0, 255, 50)), span=(2/3., 1.)),
            LinearRegionItem([0, 1], 'horizontal', swapMode='block', pen='w',
                             brush=fn.mkBrush((255, 255, 255, 50)), span=(2/3., 1.))]
        for region in self.regions:
            region.setZValue(1000)
            self.vb.addItem(region)
            region.lines[0].addMarker('<|', 0.5)
            region.lines[1].addMarker('|>', 0.5)
            region.sigRegionChanged.connect(self.regionChanging)
            region.sigRegionChangeFinished.connect(self.regionChanged)
            
        self._showRegions()
            
        self.region = self.regions[0]  # for backward compatibility.
        
        self.axis = AxisItem('left', linkView=self.vb, maxTickLength=-10)
        self.layout.addItem(self.axis, 0, 0)
        self.layout.addItem(self.vb, 0, 1)
        self.layout.addItem(self.gradient, 0, 2)
        self.range = None
        self.gradient.setFlag(self.gradient.ItemStacksBehindParent)
        self.vb.setFlag(self.gradient.ItemStacksBehindParent)
        
        #self.grid = GridItem()
        #self.vb.addItem(self.grid)
        
        self.gradient.sigGradientChanged.connect(self.gradientChanged)
        self.vb.sigRangeChanged.connect(self.viewRangeChanged)
        self.plot = PlotDataItem()
        self.plot.rotate(90)
        self.fillHistogram(fillHistogram)
            
        self.vb.addItem(self.plot)
        self.autoHistogramRange()
        
        if image is not None:
            self.setImageItem(image)
        #self.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        
    def fillHistogram(self, fill=True, level=0.0, color=(100, 100, 200)):
        if fill:
            self.plot.setFillLevel(level)
            self.plot.setFillBrush(color)
        else:
            self.plot.setFillLevel(None)
        
    #def sizeHint(self, *args):
        #return QtCore.QSizeF(115, 200)
        
    def paint(self, p, *args):
        if self.levelMode != 'mono':
            return
        
        pen = self.region.lines[0].pen
        rgn = self.getLevels()
        p1 = self.vb.mapFromViewToItem(self, Point(self.vb.viewRect().center().x(), rgn[0]))
        p2 = self.vb.mapFromViewToItem(self, Point(self.vb.viewRect().center().x(), rgn[1]))
        gradRect = self.gradient.mapRectToParent(self.gradient.gradRect.rect())
        for pen in [fn.mkPen((0, 0, 0, 100), width=3), pen]:
            p.setPen(pen)
            p.drawLine(p1 + Point(0, 5), gradRect.bottomLeft())
            p.drawLine(p2 - Point(0, 5), gradRect.topLeft())
            p.drawLine(gradRect.topLeft(), gradRect.topRight())
            p.drawLine(gradRect.bottomLeft(), gradRect.bottomRight())
        #p.drawRect(self.boundingRect())
        
        
    def setHistogramRange(self, mn, mx, padding=0.1):
        """Set the Y range on the histogram plot. This disables auto-scaling."""
        self.vb.enableAutoRange(self.vb.YAxis, False)
        self.vb.setYRange(mn, mx, padding)
        
        #d = mx-mn
        #mn -= d*padding
        #mx += d*padding
        #self.range = [mn,mx]
        #self.updateRange()
        #self.vb.setMouseEnabled(False, True)
        #self.region.setBounds([mn,mx])
        
    def autoHistogramRange(self):
        """Enable auto-scaling on the histogram plot."""
        self.vb.enableAutoRange(self.vb.XYAxes)
        #self.range = None
        #self.updateRange()
        #self.vb.setMouseEnabled(False, False)
            
    #def updateRange(self):
        #self.vb.autoRange()
        #if self.range is not None:
            #self.vb.setYRange(*self.range)
        #vr = self.vb.viewRect()
        
        #self.region.setBounds([vr.top(), vr.bottom()])

    def setImageItem(self, img):
        self.imageItem = weakref.ref(img)
        img.sigImageChanged.connect(self.imageChanged)
        img.setLookupTable(self.getLookupTable)  ## send function pointer, not the result
        #self.gradientChanged()
        self.regionChanged()
        self.imageChanged(autoLevel=True)
        #self.vb.autoRange()
        
    def viewRangeChanged(self):
        self.update()
    
    def gradientChanged(self):
        if self.imageItem() is not None:
            if self.gradient.isLookupTrivial():
                self.imageItem().setLookupTable(None) #lambda x: x.astype(np.uint8))
            else:
                self.imageItem().setLookupTable(self.getLookupTable)  ## send function pointer, not the result
            
        self.lut = None
        #if self.imageItem is not None:
            #self.imageItem.setLookupTable(self.gradient.getLookupTable(512))
        self.sigLookupTableChanged.emit(self)

    def getLookupTable(self, img=None, n=None, alpha=None):
        if n is None:
            if img.dtype == np.uint8:
                n = 256
            else:
                n = 512
        if self.lut is None:
            self.lut = self.gradient.getLookupTable(n, alpha=alpha)
        return self.lut

    def regionChanged(self):
        #if self.imageItem is not None:
            #self.imageItem.setLevels(self.region.getRegion())
        self.sigLevelChangeFinished.emit(self)
        #self.update()

    def regionChanging(self):
        if self.imageItem() is not None:
            self.imageItem().setLevels(self.region.getRegion())
        self.sigLevelsChanged.emit(self)
        self.update()

    def imageChanged(self, autoLevel=False, autoRange=False):
        profiler = debug.Profiler()
        h = self.imageItem().getHistogram()
        profiler('get histogram')
        if h[0] is None:
            return
        self.plot.setData(*h)
        profiler('set plot')
        if autoLevel:
            mn = h[0][0]
            mx = h[0][-1]
            self.region.setRegion([mn, mx])
            profiler('set region')
            
    def getLevels(self):
        return self.region.getRegion()
        
    def setLevels(self, mn, mx):
        self.region.setRegion([mn, mx])
        
    def setLevelMode(self, mode):
        """ Set the method of controlling the image levels offered to the user. 
        Options are 'mono', 'rgba', 'rgb', and 'rg'.
        """
        self.levelMode = mode
        self._showRegions()

    def _showRegions(self):
        for rgn in self.regions:
            rgn.setVisible(False)
            
        if self.levelMode in ('rg', 'rgb', 'rgba'):
            imax = len(self.levelMode)+1
            xdif = 1.0 / (imax-1)
            for i in range(1, imax):
                self.regions[i].setVisible(True)
                self.regions[i].setSpan((i-1) * xdif, i * xdif)
            self.gradient.hide()
        elif self.levelMode == 'mono':
            self.regions[0].setVisible(True)
            self.gradient.show()
        else:
            raise ValueError("Unknown level mode %r" %  self.levelMode) 
        
        self.update()
