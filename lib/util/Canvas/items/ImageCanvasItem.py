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
                elif 'Downsample' in self.handle.info():
                    opts['scale'] = self.handle.info()['pixelSize']
                    if 'microscope' in self.handle.info():
                        m = self.handle.info()['microscope']
                        print 'm: ',m
                        print 'mpos: ', m['position']
                        opts['pos'] = m['position'][0:2]
                    else:
                        info = self.data._info[-1]
                        opts['pos'] = info.get('imagePosition', None)
                else:
                    info = self.data._info[-1]
                    opts['scale'] = info.get('pixelSize', None)
                    opts['pos'] = info.get('imagePosition', None)
            except:
                #print 'uga uga boom'
                pass

        print opts

        if item is None:
            item = pg.ImageItem()
        CanvasItem.__init__(self, item, **opts)

        self.histogram = pg.PlotWidget()
        self.blockHistogram = False
        self.histogram.setMaximumHeight(100)
        self.levelRgn = pg.LinearRegionItem()
        self.histogram.addItem(self.levelRgn)

        #self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        #self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        #self.maxBtn = QtGui.QPushButton('Max')
        #self.maxBtn.clicked.connect(self.maxClicked)
        #self.layout.addWidget(self.maxBtn, self.layout.rowCount(), 0, 1, 2)


        self.updateHistogram(autoLevels=True)

        # addWidget arguments: row, column, rowspan, colspan 
        self.layout.addWidget(self.histogram, self.layout.rowCount(), 0, 1, 2)

        self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        #self.timeSlider.setMinimum(0)
        #self.timeSlider.setMaximum(self.data.shape[0]-1)
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        self.timeSlider.valueChanged.connect(self.timeChanged)
        self.timeSlider.sliderPressed.connect(self.timeSliderPressed)
        self.timeSlider.sliderReleased.connect(self.timeSliderReleased)
        thisRow = self.layout.rowCount()
        self.edgeBtn = QtGui.QPushButton('Edge')
        self.edgeBtn.clicked.connect(self.edgeClicked)
        self.layout.addWidget(self.edgeBtn, thisRow, 0, 1, 1)

        self.maxBtn2 = QtGui.QPushButton('Max w/Filter')
        self.maxBtn2.clicked.connect(self.max2Clicked)
        self.layout.addWidget(self.maxBtn2, thisRow, 1, 1, 1)

        self.meanBtn = QtGui.QPushButton('Mean')
        self.meanBtn.clicked.connect(self.meanClicked)
        self.layout.addWidget(self.meanBtn, thisRow+1, 0, 1, 1)

        self.maxBtn = QtGui.QPushButton('Max no Filter')
        self.maxBtn.clicked.connect(self.maxClicked)
        self.layout.addWidget(self.maxBtn, thisRow+1, 1, 1, 1)

        ## controls that only appear if there is a time axis
        self.timeControls = [self.timeSlider, self.edgeBtn, self.maxBtn, self.meanBtn, self.maxBtn2]

        if self.data is not None:
            self.updateImage(self.data)


        self.graphicsItem().sigImageChanged.connect(self.updateHistogram)
        self.levelRgn.sigRegionChanged.connect(self.levelsChanged)
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

    def edgeClicked(self):
        ## unsharp mask to enhance fine details
        fd = self.data.astype(float)
        blur = ndimage.gaussian_filter(fd, (0, 1, 1))
        blur2 = ndimage.gaussian_filter(fd, (0, 2, 2))
        dif = blur - blur2
        #dif[dif < 0.] = 0
        self.graphicsItem().updateImage(dif.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def maxClicked(self):
        ## just the max of a stack
        fd = self.data.astype(float)
        self.graphicsItem().updateImage(fd.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def max2Clicked(self):
        ## just the max of a stack, after a little 3d bluring
        fd = self.data.astype(float)
        blur = ndimage.gaussian_filter(fd, (1, 1, 1))
        self.graphicsItem().updateImage(blur.max(axis=0))
        self.updateHistogram(autoLevels=True)

    def meanClicked(self):
        ## just the max of a stack
        fd = self.data.astype(float)
        self.graphicsItem().updateImage(fd.mean(axis=0))
        self.updateHistogram(autoLevels=True)

#        self.updateHistogram(autoLevels=True)

    def timeSliderReleased(self):
        self.blockHistogram = False
        self.updateHistogram()


    def updateHistogram(self, autoLevels=False):
        if self.blockHistogram:
            return
        x, y = self.graphicsItem().getHistogram()
        if x is None: ## image has no data
            return
        self.histogram.clearPlots()
        self.histogram.plot(x, y)
        if autoLevels:
            self.graphicsItem().updateImage(autoLevels=True)
            w, b = self.graphicsItem().getLevels()
            self.levelRgn.blockSignals(True)
            self.levelRgn.setRegion([w, b])
            self.levelRgn.blockSignals(False)

    def updateImage(self, data, autoLevels=True):
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
            #self.timeSlider.show()
            #self.maxBtn.show()
            self.graphicsItem().updateImage(data[self.timeSlider.value()])
        else:
            #self.timeSlider.hide()
            #self.maxBtn.hide()
            self.graphicsItem().updateImage(data, autoLevels=autoLevels)

        for widget in self.timeControls:
            widget.setVisible(showTime)

        tr = self.saveTransform()
        self.resetUserTransform()
        self.restoreTransform(tr)

        self.updateHistogram(autoLevels=autoLevels)

    def levelsChanged(self):
        rgn = self.levelRgn.getRegion()
        self.graphicsItem().setLevels(rgn)
        self.hideSelectBox()

    def levelsChangeFinished(self):
        self.showSelectBox()


