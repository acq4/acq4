# -*- coding: utf-8 -*-
from __future__ import print_function
from collections import OrderedDict
from acq4.util import Qt
from .CanvasItem import CanvasItem
import numpy as np
import scipy.ndimage as ndimage
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.flowchart
import acq4.util.DataManager as DataManager
import acq4.util.debug as debug
from .itemtypes import registerItemType


class ImageCanvasItem(CanvasItem):
    """
    CanvasItem displaying an image. 
    The image may be 2 or 3-dimensional.
    Options:
        image: May be a fileHandle, ndarray, or GraphicsItem.
        handle: May optionally be specified in place of image

    """
    _typeName = "Image"
    
    def __init__(self, image=None, **opts):

        ## If no image was specified, check for a file handle..
        if image is None:
            image = opts.get('handle', None)

        item = None
        self.data = None
        
        if isinstance(image, Qt.QGraphicsItem):
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

        self.splitter = Qt.QSplitter()
        self.splitter.setOrientation(Qt.Qt.Vertical)
        self.layout.addWidget(self.splitter, self.layout.rowCount(), 0, 1, 2)
        
        self.filterGroup = pg.GroupBox("Image Filter")
        fgl = Qt.QGridLayout()
        fgl.setContentsMargins(3, 3, 3, 3)
        fgl.setSpacing(1)
        self.filterGroup.setLayout(fgl)
        self.filter = ImageFilterWidget()
        self.filter.sigStateChanged.connect(self.filterStateChanged)
        fgl.addWidget(self.filter)
        self.splitter.addWidget(self.filterGroup)

        self.histogram = pg.HistogramLUTWidget()
        self.histogram.setImageItem(self.graphicsItem())

        # addWidget arguments: row, column, rowspan, colspan 
        self.splitter.addWidget(self.histogram)

        self.imgModeCombo = Qt.QComboBox()
        self.imgModeCombo.addItems(['SourceOver', 'Overlay', 'Plus', 'Multiply'])
        self.layout.addWidget(self.imgModeCombo, self.layout.rowCount(), 0, 1, 1)
        self.imgModeCombo.currentIndexChanged.connect(self.imgModeChanged)
        
        self.autoBtn = Qt.QPushButton("Auto")
        self.autoBtn.setCheckable(True)
        self.autoBtn.setChecked(True)
        self.layout.addWidget(self.autoBtn, self.layout.rowCount()-1, 1, 1, 1)

        self.timeSlider = Qt.QSlider(Qt.Qt.Horizontal)
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
            
            # Needed to ensure selection box wraps the image properly
            tr = self.saveTransform()
            self.resetUserTransform()
            self.restoreTransform(tr)
            # Why doesn't this work?
            #self.selectBoxFromUser() ## move select box to match new bounds
            
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
        self.graphicsItem().setCompositionMode(getattr(Qt.QPainter, 'CompositionMode_' + mode))

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
            self.graphicsItem().setImage(data[self.timeSlider.value()], autoLevels=self.autoBtn.isChecked())
        else:
            self.graphicsItem().setImage(data, autoLevels=self.autoBtn.isChecked())

        for widget in self.timeControls:
            widget.setVisible(showTime)

    def saveState(self, **kwds):
        state = CanvasItem.saveState(self, **kwds)
        state['imagestate'] = self.histogram.saveState()
        state['filter'] = self.filter.saveState()
        state['composition'] = self.imgModeCombo.currentText()
        return state
    
    def restoreState(self, state):
        CanvasItem.restoreState(self, state)
        self.filter.restoreState(state['filter'])
        self.imgModeCombo.setCurrentIndex(self.imgModeCombo.findText(state['composition']))
        self.histogram.restoreState(state['imagestate'])

registerItemType(ImageCanvasItem)


class ImageFilterWidget(Qt.QWidget):
    
    sigStateChanged = Qt.Signal()
    
    def __init__(self):
        Qt.QWidget.__init__(self)
        
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        # Set up filter buttons
        self.btns = OrderedDict()
        row, col = 0, 0
        for name in ['Mean', 'Max', 'Max w/Gaussian', 'Max w/Median', 'Edge']:
            btn = Qt.QPushButton(name)
            self.btns[name] = btn
            btn.setCheckable(True)
            self.layout.addWidget(btn, row, col)
            btn.clicked.connect(self.filterBtnClicked)
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        # show flowchart control panel inside a collapsible group box
        self.fcGroup = pg.GroupBox('Filter Settings')
        fgl = Qt.QVBoxLayout()
        self.fcGroup.setLayout(fgl)
        fgl.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.fcGroup, row+1, 0, 1, 2)
        self.fc = pg.flowchart.Flowchart(terminals={'dataIn': {'io':'in'}, 'dataOut': {'io':'out'}})
        fgl.addWidget(self.fc.widget())
        self.fcGroup.setCollapsed(True)
        self.fc.sigStateChanged.connect(self.sigStateChanged)

    def filterBtnClicked(self, checked):
        # remember slice before clearing fc
        snode = self.fc.nodes().get('Slice', None)
        if snode is not None:
            snstate = snode.saveState()
        else:
            snstate = None
        print(snstate)
        
        self.fc.clear()
        
        if not checked:
            return
        btn = self.sender()
        
        # uncheck all other filter btns
        for b in self.btns.values():
            if b is not btn:
                b.setChecked(False)
        
        name = btn.text()
        if name == 'Mean':
            s = self.fc.createNode('Slice', name="Slice")
            m = self.fc.createNode('Mean', name="Mean", pos=[150, 0])
            self.fc.connectTerminals(self.fc['dataIn'], s['In'])
            self.fc.connectTerminals(s['Out'], m['In'])
            self.fc.connectTerminals(m['Out'], self.fc['dataOut'])
        elif name == 'Max':
            s = self.fc.createNode('Slice', name="Slice")
            m = self.fc.createNode('Max', name="Max", pos=[150, 0])
            self.fc.connectTerminals(self.fc['dataIn'], s['In'])
            self.fc.connectTerminals(s['Out'], m['In'])
            self.fc.connectTerminals(m['Out'], self.fc['dataOut'])
        elif name == 'Max w/Gaussian':
            s = self.fc.createNode('Slice', name="Slice", pos=[-40, 0])
            f = self.fc.createNode('GaussianFilter', name="GaussianFilter", pos=[70, 0])
            m = self.fc.createNode('Max', name="Max", pos=[180, 0])
            self.fc.connectTerminals(self.fc['dataIn'], s['In'])
            self.fc.connectTerminals(s['Out'], f['In'])
            self.fc.connectTerminals(f['Out'], m['In'])
            self.fc.connectTerminals(m['Out'], self.fc['dataOut'])
        elif name == 'Max w/Median':
            s = self.fc.createNode('Slice', name="Slice", pos=[-40, 0])
            f = self.fc.createNode('MedianFilter', name="MedianFilter", pos=[70, 0])
            m = self.fc.createNode('Max', name="Max", pos=[180, 0])
            self.fc.connectTerminals(self.fc['dataIn'], s['In'])
            self.fc.connectTerminals(s['Out'], f['In'])
            self.fc.connectTerminals(f['Out'], m['In'])
            self.fc.connectTerminals(m['Out'], self.fc['dataOut'])
        elif name == 'Edge':
            s = self.fc.createNode('Slice', name="Slice", pos=[-40, 0])
            f1 = self.fc.createNode('PythonEval', name='GaussDiff', pos=[70, 0])
            f1.setCode("""
                from scipy.ndimage import gaussian_filter
                img = args['input'].astype(float)
                edge = gaussian_filter(img, (0, 2, 2)) - gaussian_filter(img, (0, 1, 1))
                return {'output': edge} 
            """)
            m = self.fc.createNode('Max', name="Max", pos=[180, 0])
            self.fc.connectTerminals(self.fc['dataIn'], s['In'])
            self.fc.connectTerminals(s['Out'], f1['input'])
            self.fc.connectTerminals(f1['output'], m['In'])
            self.fc.connectTerminals(m['Out'], self.fc['dataOut'])

        # restore slice is possible
        if snstate is not None:
            snode = self.fc.nodes().get('Slice', None)
            if snode is not None:
                print("restore!")
                snode.restoreState(snstate)
        
    def setInput(self, img):
        self.fc.setInput(dataIn=img)
        
    def output(self):
        return self.fc.output()['dataOut']

    def process(self, img):
        return self.fc.process(dataIn=img)['dataOut']

    def saveState(self):
        return {'flowchart': self.fc.saveState()}
    
    def restoreState(self, state):
        self.fc.restoreState(state['flowchart'])
