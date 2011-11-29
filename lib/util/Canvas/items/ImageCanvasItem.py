# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from CanvasItem import CanvasItem
import numpy as np
import scipy.ndimage as ndimage
import pyqtgraph as pg
import DataManager

class ImageCanvasItem(CanvasItem):
    def __init__(self, image=None, **opts):
        """
        CanvasItem displaying an image. 
        The image may be 2 or 3-dimensional.
        Options:
            image: May be a fileHandle, ndarray, or GraphicsItem.
            handle: May optionally be specified in place of image
        
        """
        
        ## If no image was specified, check for a file handle..
        if image is None:
            image = opts.get('handle', None)
            #try:
                #image = opts['handle']
            #except KeyError:
                #raise Exception("ImageCanvasItem must be initialized with either an image or an image file handle.")
        
        item = None
        self.data = None
        if isinstance(image, QtGui.QGraphicsItem):
            item = image
        elif isinstance(image, np.ndarray):
            self.data = image
        elif isinstance(image, DataManager.FileHandle):
            opts['handle'] = image
            self.handle = image
            self.data = self.handle.read()
            
            #item = graphicsItems.ImageItem(self.data)
            if 'name' not in opts:
                opts['name'] = self.handle.shortName()

            try:
                if 'imagePosition' in self.handle.info():
                    opts['scale'] = self.handle.info()['pixelSize']
                    opts['pos'] = self.handle.info()['imagePosition']
                else:
                    info = self.data._info[-1]
                    if 'imagePosition' in info:
                        opts['pos'] = info['imagePosition']
                    if 'pixelSize' in info:
                        opts['scale'] = info['pixelSize']
            except:
                pass
        
        if item is None:
            item = pg.ImageItem()
        CanvasItem.__init__(self, item, **opts)
        
        
        
        self.histogram = pg.PlotWidget()
        self.blockHistogram = False
        self.histogram.setMaximumHeight(100)
        self.levelRgn = pg.LinearRegionItem(self.histogram)
        self.histogram.addItem(self.levelRgn)

        self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        self.maxBtn = QtGui.QPushButton('Max')
        self.maxBtn.clicked.connect(self.maxClicked)
        self.layout.addWidget(self.maxBtn, self.layout.rowCount(), 0, 1, 2)


        self.updateHistogram(autoRange=True)
        
        self.layout.addWidget(self.histogram, self.layout.rowCount(), 0, 1, 2)
        
        if self.data is not None:
            self.updateImage(self.data)
        
        
        
        #self.item.connect(self.item, QtCore.SIGNAL('imageChanged'), self.updateHistogram)
        self.graphicsItem().sigImageChanged.connect(self.updateHistogram)
        #self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChanged'), self.levelsChanged)
        self.levelRgn.sigRegionChanged.connect(self.levelsChanged)
        #self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChangeFinished'), self.levelsChangeFinished)
        self.levelRgn.sigRegionChangeFinished.connect(self.levelsChangeFinished)
        
    @classmethod
    def checkFile(cls, fh):
        if not fh.isFile():
            return 0
        ext = fh.ext().lower()
        if ext == '.ma':
            return 10
        elif ext in ['.ma', '.png', '.jpg', '.tif']:
            return 100
        
        return 0

        #self.timeSlider
        
    def timeChanged(self, t):
        self.graphicsItem().updateImage(self.data[t])
        
    def timeSliderPressed(self):
        self.blockHistogram = True
        
        
    def maxClicked(self):
        ## unsharp mask to enhance fine details
        fd = self.data.astype(float)
        blur = ndimage.gaussian_filter(fd, (0, 1, 1))
        blur2 = ndimage.gaussian_filter(fd, (0, 2, 2))
        dif = blur - blur2
        #dif[dif < 0.] = 0
        self.graphicsItem().updateImage(dif.max(axis=0))
        self.updateHistogram(autoRange=True)
            
        
    def timeSliderReleased(self):
        self.blockHistogram = False
        self.updateHistogram()
        
        
    def updateHistogram(self, autoRange=False):
        if self.blockHistogram:
            return
        x, y = self.graphicsItem().getHistogram()
        if x is None: ## image has no data
            return
        self.histogram.clearPlots()
        self.histogram.plot(x, y)
        if autoRange:
            self.graphicsItem().updateImage(autoRange=True)
            w, b = self.graphicsItem().getLevels()
            self.levelRgn.blockSignals(True)
            self.levelRgn.setRegion([w, b])
            self.levelRgn.blockSignals(False)
            
    def updateImage(self, data, autoRange=True):
        self.data = data
        if data.ndim == 4:
            showTime = True
        elif data.ndim == 3:
            if data.shape[2] <= 4: ## assume last axis is color
                showTime = False
            else:
                showTime = True
        else:
            showTime = False
            
        if showTime:
            self.timeSlider.setMinimum(0)
            self.timeSlider.setMaximum(self.data.shape[0]-1)
            self.timeSlider.valueChanged.connect(self.timeChanged)
            self.timeSlider.sliderPressed.connect(self.timeSliderPressed)
            self.timeSlider.sliderReleased.connect(self.timeSliderReleased)
            self.timeSlider.show()
            self.maxBtn.show()
            self.graphicsItem().updateImage(data[self.timeSlider.value()])
        else:
            self.timeSlider.hide()
            self.maxBtn.hide()
            self.graphicsItem().updateImage(data)
            
        tr = self.saveTransform()
        self.resetUserTransform()
        self.restoreTransform(tr)
            
        self.updateHistogram(autoRange=autoRange)
        
    def levelsChanged(self):
        rgn = self.levelRgn.getRegion()
        self.graphicsItem().setLevels(rgn[1], rgn[0])
        self.hideSelectBox()

    def levelsChangeFinished(self):
        self.showSelectBox()
