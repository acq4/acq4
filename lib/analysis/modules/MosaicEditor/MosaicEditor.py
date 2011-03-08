# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
#from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import numpy as np
#import FileLoader
#import DatabaseGui
#import FeedbackButton
from MosaicEditorTemplate import *
import DataManager
import lib.analysis.atlas as atlas

class MosaicEditor(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrl = QtGui.QWidget()
        self.ui = Ui_Form()
        self.ui.setupUi(self.ctrl)
        self.atlas = None
        
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            ('Mosaic', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('right',), 'size': (600, 200)}),
            ('Canvas', {'type': 'canvas', 'pos': ('bottom', 'Mosaic'), 'size': (600, 600)}),
        ])
        
        self.initializeElements()

        self.ui.canvas = self.getElement('Canvas', create=True)
        self.items = {}
        self.cells = {}
        
        addScanImagesBtn = QtGui.QPushButton()
        addScanImagesBtn.setText('Add Scan Image')
        self.ui.fileLoader = self.getElement('File Loader', create=True)
        self.ui.fileLoader.ui.fileTree.hide()
        self.ui.fileLoader.ui.verticalLayout_2.addWidget(addScanImagesBtn)
        
        
        
        
        for a in atlas.listAtlases():
            self.ui.atlasCombo.addItem(a)
        
        self.connect(self.ui.canvas, QtCore.SIGNAL('itemTransformChangeFinished'), self.itemMoved)
        self.connect(addScanImagesBtn, QtCore.SIGNAL('clicked()'), self.loadScanImage)
        #self.ui.exportSvgBtn.clicked.connect(self.exportSvg)
        self.ui.atlasCombo.currentIndexChanged.connect(self.atlasComboChanged)
        #self.ui.normalizeBtn.clicked.connect(self.normalizeImages)

    def atlasComboChanged(self, ind):
        if ind == 0:
            return
        name = self.ui.atlasCombo.currentText()
        self.loadAtlas(name)

    def loadAtlas(self, name):
        name = str(name)
        if self.atlas is not None:
            self.atlas.close()
        
        cls = atlas.getAtlasClass(name)
        obj = cls(self.getElement('Canvas'))
        ctrl = obj.ctrlWidget()
        self.ui.atlasLayout.addWidget(ctrl, 0, 0)
        self.atlas = obj
        

    def loadFileRequested(self, f):
        canvas = self.getElement('Canvas')
        if f is None:
            return
            
        if f.info().get('dirType', None) == 'Cell':
            item = canvas.addMarker(handle=f, scale=[20e-6,20e-6])
            self.items[item] = f
        else:
            item = canvas.addFile(f, separateParams=False)
            self.items[item] = f
            
            item.timestamp = f.info()['__timestamp__']
            if not item.hasUserTransform():
                ## Record the timestamp for this file, see what is the most recent transformation to copy
                best = None
                for i2 in self.items:
                    if i2 is item:
                        continue
                    if not hasattr(i2, 'timestamp'):
                        continue
                    if i2.timestamp < item.timestamp:
                        if best is None or i2.timestamp > best.timestamp:
                            best = i2
                            
                if best is None:
                    return
                    
                trans = best.saveTransform()
                item.restoreTransform(trans)
                
        canvas.selectItem(item)
        
    def loadScanImage(self):
        print 'loadScanImage called.'
        dh = self.ui.fileLoader.ui.dirTree.selectedFile()
        dirs = [dh[d] for d in dh.subDirs()]
        if 'Camera' not in dirs[0].subDirs():
            print "No image data for this scan."
            return
        
        images = []
        for d in dirs:
            frames = d['Camera']['frames.ma'].read()
            image = frames[1]-frames[0]
            image[image > frames[1].max()*2] = 0.
            image = (image/float(image.max()) * 1000)
            images.append(image)
            
        scanImages = np.zeros(images[0].shape)
        for im in images:
            scanImages += im
        
        info = dirs[0]['Camera']['frames.ma'].read()._info[-1]
    
        pos =  info['imagePosition']
        scale = info['pixelSize']
        item = self.getElement('Canvas').addImage(scanImages, pos=pos, scale=scale, name='scanImage')
        self.items[item] = scanImages
            

    def itemMoved(self, canvas, item):
        """Save an item's transformation if the user has moved it. 
        This is saved in the 'userTransform' attribute; the original position data is not affected."""
        if item not in self.items:
            return
        fh = self.items[item]
        trans = item.saveTransform()
        if hasattr(fh, 'setInfo'):
            fh.setInfo(userTransform=trans)
        #print fh, "moved"
        
    #def exportSvg(self):
        #self.ui.canvas.view.writeSvg()