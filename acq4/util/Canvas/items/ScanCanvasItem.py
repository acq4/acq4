# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from .CanvasItem import CanvasItem
from .ImageCanvasItem import ImageCanvasItem
import acq4.Manager
import pyqtgraph as pg
import numpy as np
from .itemtypes import registerItemType

Ui_Form = Qt.importTemplate('.ScanCanvasItemTemplate')


class ScanCanvasItem(CanvasItem):
    """
    CanvasItem representing a photostimulation scan.
    Options:
        handle: DirHandle where scan data is stored (required)
        subDirs: list of DirHandles to the individual Protocols for each spot 
                    (optional; this allows the inclusion of only part of a scan sequence)
    """
    _typeName = "Scan"
    
    def __init__(self, **opts):
        self.defaultSize = 1e-4 # set a default spot size as 100 um.
        if 'handle' not in opts:
            raise Exception("ScanCanvasItem must be initialized with 'handle' or 'handles' specified in opts")
        
        ## Top-level dirHandle tells us the default name of the item 
        ## and may have a userTransform
        dirHandle = opts['handle']
        if 'name' not in opts:
            opts['name'] = dirHandle.shortName()
            
        ## Get the specific list of subdirectory to use from which to pull spot information
        if 'subDirs' in opts:
            dirs = opts['subDirs']
        else:
            model = acq4.Manager.getManager().dataModel
            typ = model.dirType(dirHandle)
            if typ == 'ProtocolSequence':
                dirs = [dirHandle[d] for d in dirHandle.subDirs()]
            elif typ == 'Protocol':
                dirs = [dirHandle]
            else:
                raise Exception("Invalid dir type '%s'" % typ)

        ## Generate spot data and a scatterplotitem
        pts = []
        for d in dirs:
            if 'Scanner' in d.info() and 'position' in d.info()['Scanner']: #Note: this is expected to fail (gracefully) when a protocol sequence is incomplete
                pos = d.info()['Scanner']['position']
                if 'spotSize' in d.info()['Scanner']:
                    size = d.info()['Scanner']['spotSize']
                else:
                    size = self.defaultSize
                pts.append({'pos': pos, 'size': size, 'data': d})
        self.scatterPlotData = pts
        if len(pts) == 0:
            raise Exception("No data found in scan %s." % dirHandle.name(relativeTo=dirHandle.parent().parent()))
        gitem = pg.ScatterPlotItem(pts, pxMode=False, pen=(50,50,50,200))
        CanvasItem.__init__(self, gitem, **opts)
        self.originalSpotSize = size
        
        self._ctrlWidget = Qt.QWidget()
        self.ui = Ui_Form()
        self.ui.setupUi(self._ctrlWidget)
        self.layout.addWidget(self._ctrlWidget, self.layout.rowCount(), 0, 1, 2)
        self.ui.outlineColorBtn.setColor((50,50,50,200))
        
        self.ui.sizeSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[1e-6, None])
        self.ui.sizeSpin.setValue(self.originalSpotSize)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        self.ui.sizeFromCalibrationRadio.clicked.connect(self.updateSpotSize)
        self.ui.outlineColorBtn.sigColorChanging.connect(self.updateOutline)
        
        self.addScanImageBtn = self.ui.loadSpotImagesBtn
        self.addScanImageBtn.connect(self.addScanImageBtn, Qt.SIGNAL('clicked()'), self.loadScanImage)
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile():
            return 0
        try:
            model = acq4.Manager.getManager().dataModel
            typ = model.dirType(fh)
            if typ == 'ProtocolSequence':  ## should do some deeper inspection here..
                return 10
            elif typ == 'Protocol':
                return 10
            return 0
        except AttributeError:
            return 0
    
    def loadScanImage(self):
        dh = self.opts['handle']
        dirs = [dh[d] for d in dh.subDirs()]
        if 'Camera' not in dirs[0].subDirs():
            print("No image data for this scan.")
            return
        
        spotFrame = self.ui.spotFrameSpin.value()
        bgFrame = self.ui.bgFrameSpin.value()
        
        images = []
        handles = []
        nulls = []
        with pg.ProgressDialog("Loading scan images..", 0, len(dirs)) as dlg:
            for d in dirs:
                if 'Camera' not in d.subDirs():
                    continue
                fh = d['Camera']['frames.ma']
                handles.append(fh)
                frames = fh.read().asarray()
                if self.ui.bgFrameCheck.isChecked():
                    image = frames[spotFrame]-frames[bgFrame]
                    image[frames[bgFrame] > frames[spotFrame]] = 0.  ## unsigned type; avoid negative values
                else:
                    image = frames[spotFrame]
                    
                mx = image.max()
                image *= (1000. / mx)
                images.append(image)
                if mx < 50:
                    nulls.append(d.shortName())
                dlg += 1
                if dlg.wasCanceled():
                    raise Exception("Processing canceled by user")                
            
            #print "Null frames for %s:" %dh.shortName(), nulls
            dlg.setLabelText("Processing scan images..")
            dlg.setValue(0)
            dlg.setMaximum(len(images))
            scanImages = np.zeros(images[0].shape)
            for im in images:
                mask = im > scanImages
                scanImages[mask] = im[mask]
                dlg += 1
                if dlg.wasCanceled():
                    raise Exception("Processing canceled by user")                
        
        image = ScanImageCanvasItem(scanImages, handles, z=self.opts['z']-1)
        item = self.canvas.addItem(image)
        self.scanImage = item
        
    def sizeSpinEdited(self):
        self.ui.sizeCustomRadio.setChecked(True)
        self.updateSpotSize()

    def updateSpotSize(self):
        size = self.getSpotSize()
        for p in self.scatterPlotData:
            p['size'] = size
        self.graphicsItem().setPoints(self.scatterPlotData)
        
    def getSpotSize(self):
        if self.ui.sizeCustomRadio.isChecked():
            size = self.ui.sizeSpin.value()
        elif self.ui.sizeFromCalibrationRadio.isChecked():
            self.ui.sizeSpin.valueChanged.disconnect(self.sizeSpinEdited)
            self.ui.sizeSpin.setValue(self.originalSpotSize)
            self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
            size = self.originalSpotSize
        return size

    def updateOutline(self):
        color = self.ui.outlineColorBtn.color()
        self.graphicsItem().setPen(color)
        
    def createGradient(self):
       # Generate a current scale bar from the console:

        # some of this from command line...
 
        man = acq4.Manager.getManager()
        pm = man.getInterface('analysisMod', 'Photostim')
        gradnum = self.gradientNumber.value()
        # get the current color gradient. If you have multiple lines in the color mapper, you may need to 
        # change the index to 'items'
        nitems =len(pm.mapper.items)
        if gradnum >= nitems:
            gradnum = nitems-1
            self.gradientNumber.setValue(gradnum)
        colormap = pm.mapper.items[gradnum] 
        gradient = colormap.gradient.getGradient()

        # build a legend
        self.gradientLegend = pg.GradientLegend((50, 150), (-10, -10))
        self.gradientLegend.scale(1, -1)  # optional, depending on whether the canvas is y-inverted
        self.gradientLegend.setGradient(gradient)

        # A full set of labels:
        self.gradientLegend.setLabels(dict((('- %3.1f' % x), x) for x in np.arange(0, 1+0.2, 0.2))) 
        # now show it
        self.canvas.addGraphicsItem(self.gradientLegend, name = 'Gradient_%d' % gradnum)

        #The '-' puts a tick mark about at the right location. That's the best I can do without writing a routine to actually put ticks on the gradient bar. 

    def removeGradient(self):
        self.canvas.removeItem(self.gradientLegend)
        
registerItemType(ScanCanvasItem)

        
class ScanImageCanvasItem(ImageCanvasItem):
    def __init__(self, img, handles, **kargs):
        self.img = img
        self.handles = handles
        ImageCanvasItem.__init__(self, self.handles[0], **kargs)
        self.graphicsItem().updateImage(self.img)
        self.updateHistogram(autoLevels=True)

    def storeUserTransform(self, fh=None):
        trans = self.saveTransform()
        for fh in self.handles:
            fh.setInfo(userTransform=trans)
            
    @classmethod
    def checkFile(self, fh):
        return 0
