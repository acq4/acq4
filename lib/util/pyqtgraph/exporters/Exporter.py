from pyqtgraph.parametertree import Parameter
from pyqtgraph.widgets.FileDialog import FileDialog
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore, QtSvg
import os
import numpy as np
LastExportDirectory = None


class Exporter(object):
    """
    Abstract class used for exporting graphics to file / printer / whatever.
    """    

    def __init__(self, item):
        """
        Initialize with the item to be exported.
        Can be an individual graphics item or a scene.
        """
        object.__init__(self)
        self.item = item
        
    def item(self):
        return self.item
    
    def parameters(self):
        """Return the parameters used to configure this exporter."""
        raise Exception("Abstract method must be overridden in subclass.")
        
    def export(self):
        """"""
        raise Exception("Abstract method must be overridden in subclass.")

    def fileSaveDialog(self, filter=None, opts=None):
        ## Show a file dialog, call self.export(fileName) when finished.
        if opts is None:
            opts = {}
        self.fileDialog = FileDialog()
        self.fileDialog.setFileMode(QtGui.QFileDialog.AnyFile)
        self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
        if filter is not None:
            if isinstance(filter, basestring):
                self.fileDialog.setNameFilter(filter)
            elif isinstance(filter, list):
                self.fileDialog.setNameFilters(filter)
        global LastExportDirectory
        exportDir = LastExportDirectory
        if exportDir is not None:
            self.fileDialog.setDirectory(exportDir)
        self.fileDialog.show()
        self.fileDialog.opts = opts
        self.fileDialog.fileSelected.connect(self.fileSaveFinished)
        return
        
    def fileSaveFinished(self, fileName):
        fileName = str(fileName)
        global LastExportDirectory
        LastExportDirectory = os.path.split(fileName)[0]
        self.export(fileName=fileName, **self.fileDialog.opts)
        
        
    def getScene(self):
        if isinstance(self.item, pg.GraphicsScene):
            return self.item
        else:
            return self.item.scene()
        
    def getSourceRect(self):
        if isinstance(self.item, pg.GraphicsScene):
            return self.item.getViewWidget().viewRect()
        else:
            return self.item.sceneBoundingRect()
        
    def getTargetRect(self):        
        if isinstance(self.item, pg.GraphicsScene):
            return self.item.getViewWidget().rect()
        else:
            return self.item.mapRectToDevice(self.item.boundingRect())
        
        
class SVGExporter(Exporter):
    Name = "Scalable Vector Graphics (SVG)"
    def __init__(self, item):
        Exporter.__init__(self, item)
        tr = self.getTargetRect()
        self.params = Parameter(name='params', type='group', children=[
            {'name': 'width', 'type': 'float', 'value': tr.width(), 'limits': (0, None)},
            {'name': 'height', 'type': 'float', 'value': tr.height(), 'limits': (0, None)},
        ])
        self.params.param('width').sigValueChanged.connect(self.widthChanged)
        self.params.param('height').sigValueChanged.connect(self.heightChanged)

    def widthChanged(self):
        sr = self.getSourceRect()
        ar = sr.height() / sr.width()
        self.params.param('height').setValue(self.params['width'] * ar, blockSignal=self.heightChanged)
        
    def heightChanged(self):
        sr = self.getSourceRect()
        ar = sr.width() / sr.height()
        self.params.param('width').setValue(self.params['height'] * ar, blockSignal=self.widthChanged)
        
    def parameters(self):
        return self.params
    
    def export(self, fileName=None):
        if fileName is None:
            self.fileSaveDialog(filter="Scalable Vector Graphics (*.svg)")
            return
        self.svg = QtSvg.QSvgGenerator()
        self.svg.setFileName(fileName)
        self.svg.setSize(QtCore.QSize(100,100))
        #self.svg.setResolution(600)
        #self.svg.setViewBox()
        targetRect = QtCore.QRect(0, 0, self.params['width'], self.params['height'])
        sourceRect = self.getSourceRect()
        painter = QtGui.QPainter(self.svg)
        self.getScene().render(painter, QtCore.QRectF(targetRect), sourceRect)
            
class ImageExporter(Exporter):
    Name = "Image File (PNG, TIF, JPG, ...)"
    def __init__(self, item):
        Exporter.__init__(self, item)
        tr = self.getTargetRect()
        
        self.params = Parameter(name='params', type='group', children=[
            {'name': 'width', 'type': 'int', 'value': tr.width(), 'limits': (0, None)},
            {'name': 'height', 'type': 'int', 'value': tr.height(), 'limits': (0, None)},
            {'name': 'antialias', 'type': 'bool', 'value': True},
            {'name': 'background', 'type': 'color', 'value': (0,0,0,255)},
        ])
        self.params.param('width').sigValueChanged.connect(self.widthChanged)
        self.params.param('height').sigValueChanged.connect(self.heightChanged)
        
    def widthChanged(self):
        sr = self.getSourceRect()
        ar = sr.height() / sr.width()
        self.params.param('height').setValue(self.params['width'] * ar, blockSignal=self.heightChanged)
        
    def heightChanged(self):
        sr = self.getSourceRect()
        ar = sr.width() / sr.height()
        self.params.param('width').setValue(self.params['height'] * ar, blockSignal=self.widthChanged)
        
    def parameters(self):
        return self.params
    
    def export(self, fileName=None):
        if fileName is None:
            filter = ["*."+str(f) for f in QtGui.QImageWriter.supportedImageFormats()]
            preferred = ['*.png', '*.tif', '*.jpg']
            for p in preferred[::-1]:
                if p in filter:
                    filter.remove(p)
                    filter.insert(0, p)
            self.fileSaveDialog(filter=filter)
            return
            
        targetRect = QtCore.QRect(0, 0, self.params['width'], self.params['height'])
        sourceRect = self.getSourceRect()
        #self.png = QtGui.QImage(targetRect.size(), QtGui.QImage.Format_ARGB32)
        #self.png.fill(pyqtgraph.mkColor(self.params['background']))
        bg = np.empty((self.params['width'], self.params['height'], 4), dtype=np.ubyte)
        color = self.params['background']
        bg[:,:,0] = color.blue()
        bg[:,:,1] = color.green()
        bg[:,:,2] = color.red()
        bg[:,:,3] = color.alpha()
        self.png = pg.makeQImage(bg, alpha=True)
        painter = QtGui.QPainter(self.png)
        self.getScene().render(painter, QtCore.QRectF(targetRect), sourceRect)
        self.png.save(fileName)
        
    #def writePs(self, fileName=None, item=None):
        #if fileName is None:
            #self.fileSaveDialog(self.writeSvg, filter="PostScript (*.ps)")
            #return
        #if item is None:
            #item = self
        #printer = QtGui.QPrinter(QtGui.QPrinter.HighResolution)
        #printer.setOutputFileName(fileName)
        #painter = QtGui.QPainter(printer)
        #self.render(painter)
        #painter.end()
    
    #def writeToPrinter(self):
        #pass
