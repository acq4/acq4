# -*- coding: utf-8 -*-
from acq4.pyqtgraph.Qt import QtCore, QtGui
from CanvasItem import CanvasItem
import numpy as np
import scipy.ndimage as ndimage
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.flowchart
import acq4.util.DataManager as DataManager
import acq4.util.debug as debug


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

            if 'name' not in opts:
                opts['name'] = self.handle.shortName()

            try:
                if 'transform' in self.handle.info():
                    tr = pg.SRTTransform3D(self.handle.info()['transform'])
                    tr = pg.SRTTransform(tr)  ## convert to 2D
                    opts['pos'] = tr.getTranslation()
                    opts['scale'] = tr.getScale()
                    opts['angle'] = tr.getRotation()
                else:  ## check for older info formats
                    if 'imagePosition' in self.handle.info():
                        opts['scale'] = self.handle.info()['pixelSize']
                        opts['pos'] = self.handle.info()['imagePosition']
                    elif 'Downsample' in self.handle.info():
                        ### Needed to support an older format stored by 2p imager
                        if 'pixelSize' in self.handle.info():
                            opts['scale'] = self.handle.info()['pixelSize']
                        if 'microscope' in self.handle.info():
                            m = self.handle.info()['microscope']
                            opts['pos'] = m['position'][0:2]
                        else:
                            info = self.data._info[-1]
                            opts['pos'] = info.get('imagePosition', None)
                    elif hasattr(self.data, '_info'):
                        info = self.data._info[-1]
                        opts['scale'] = info.get('pixelSize', None)
                        opts['pos'] = info.get('imagePosition', None)
                    else:
                        opts['defaultUserTransform'] = {'scale': (1e-5, 1e-5)}
                        opts['scalable'] = True
            except:
                debug.printExc('Error reading transformation for image file %s:' % image.name())

        if item is None:
            item = pg.ImageItem()
        CanvasItem.__init__(self, item, **opts)

        self.splitter = QtGui.QSplitter()
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.layout.addWidget(self.splitter, self.layout.rowCount(), 0, 1, 2)
        
        self.filter = ImageFilterWidget()
        self.filter.sigStateChanged.connect(self.filterStateChanged)
        self.splitter.addWidget(self.filter)

        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setImageItem(self.graphicsItem())
        self.blockHistogram = False

        # addWidget arguments: row, column, rowspan, colspan 
        self.splitter.addWidget(self.histogram)

        self.imgModeCombo = QtGui.QComboBox()
        self.imgModeCombo.addItems(['SourceOver', 'Overlay', 'Plus', 'Multiply'])
        self.layout.addWidget(self.imgModeCombo, self.layout.rowCount(), 0, 1, 2)
        self.imgModeCombo.currentIndexChanged.connect(self.imgModeChanged)

        self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
        self.timeSlider.valueChanged.connect(self.timeChanged)

        # ## controls that only appear if there is a time axis
        self.timeControls = [self.timeSlider]

        if self.data is not None:
            if isinstance(self.data, pg.metaarray.MetaArray):
                self.filter.setInput(self.data.asarray())
            else:
                self.filter.setInput(self.data)
            self.updateImage()

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

    def timeChanged(self, t):
        self.updateImage()

    def imgModeChanged(self):
        mode = str(self.imgModeCombo.currentText())
        self.graphicsItem().setCompositionMode(getattr(QtGui.QPainter, 'CompositionMode_' + mode))

    def filterStateChanged(self):
        self.updateImage()

    def updateImage(self):
        img = self.graphicsItem()

        # Try running data through flowchart filter
        data = self.filter.output()
        if data is None:
            data = self.data

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
            self.timeSlider.setMaximum(data.shape[0]-1)
            self.graphicsItem().setImage(data[self.timeSlider.value()])
        else:
            self.graphicsItem().setImage(data)

        for widget in self.timeControls:
            widget.setVisible(showTime)

        tr = self.saveTransform()
        self.resetUserTransform()
        self.restoreTransform(tr)


class ImageFilterWidget(QtGui.QWidget):
    
    sigStateChanged = QtCore.Signal()
    
    def __init__(self):
        QtGui.QWidget.__init__(self)
        
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        
        self.btns = {}
        self.btns['mean'] = QtGui.QPushButton('Mean')
        self.btns['mean'].clicked.connect(self.meanClicked)
        self.layout.addWidget(self.btns['mean'], 0, 0)
        
        # show flowchart control panel inside a collapsible group box
        self.fcGroup = pg.GroupBox('Filter Flowchart')
        fgl = QtGui.QVBoxLayout()
        self.fcGroup.setLayout(fgl)
        fgl.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.fcGroup, 1, 0)
        self.fc = pg.flowchart.Flowchart(terminals={'dataIn': {'io':'in'}, 'dataOut': {'io':'out'}})
        fgl.addWidget(self.fc.widget())
        self.fc.sigStateChanged.connect(self.sigStateChanged)

    def meanClicked(self):
        self.fc.clear()
        s = self.fc.createNode('Slice')
        m = self.fc.createNode('Mean')
        self.fc.connectTerminals(self.fc['dataIn'], s['In'])
        self.fc.connectTerminals(s['Out'], m['In'])
        self.fc.connectTerminals(m['Out'], self.fc['dataOut'])
        
    def setInput(self, img):
        self.fc.setInput(dataIn=img)
        
    def output(self):
        return self.fc.output()['dataOut']

    def process(self, img):
        return self.fc.process(dataIn=img)['dataOut']
