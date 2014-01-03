# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from acq4.analysis.AnalysisModule import AnalysisModule
#from flowchart import *
import os
from collections import OrderedDict
import acq4.util.debug as debug
import numpy as np
import weakref
#import FileLoader
#import DatabaseGui
#import FeedbackButton
from MosaicEditorTemplate import *
import acq4.util.DataManager as DataManager
import acq4.analysis.atlas as atlas

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
            ('Canvas', {'type': 'canvas', 'pos': ('bottom', 'Mosaic'), 'size': (600, 800), 'args': {'name': 'MosaicEditor'}}),
        ])

        self.initializeElements()

        self.ui.canvas = self.getElement('Canvas', create=True)
        self.items = weakref.WeakKeyDictionary()
        self.files = weakref.WeakValueDictionary()
        self.cells = {}
        #self.loaded = []
        
        #addScanImagesBtn = QtGui.QPushButton()
        #addScanImagesBtn.setText('Add Scan Image')
        self.ui.fileLoader = self.getElement('File Loader', create=True)
        self.ui.fileLoader.ui.fileTree.hide()
        #self.ui.fileLoader.ui.verticalLayout_2.addWidget(addScanImagesBtn)
        try:
            self.ui.fileLoader.setBaseClicked() # get the currently selected directory in the DataManager
        except:
            pass

        for a in atlas.listAtlases():
            self.ui.atlasCombo.addItem(a)

        self.ui.canvas.sigItemTransformChangeFinished.connect(self.itemMoved)
        #self.ui.exportSvgBtn.clicked.connect(self.exportSvg)
        self.ui.atlasCombo.currentIndexChanged.connect(self.atlasComboChanged)
        #self.ui.normalizeBtn.clicked.connect(self.normalizeImages)

    def atlasComboChanged(self, ind):
        if ind == 0:
            self.closeAtlas()
            return
        name = self.ui.atlasCombo.currentText()
        self.loadAtlas(name)

    def closeAtlas(self):
        if self.atlas is not None:
            self.atlas.close()
            self.atlas = None
        while True:
            ch = self.ui.atlasLayout.takeAt(0)
            if ch is None:
                break
            ch = ch.widget()
            ch.hide()
            ch.setParent(None)
        
    def loadAtlas(self, name):
        name = str(name)
        self.closeAtlas()
        
        cls = atlas.getAtlasClass(name)
        #if name == 'AuditoryCortex':
        #    obj = cls(canvas=self.getElement('Canvas'))
        #else:
             #obj = cls()
        obj = cls()
        ctrl = obj.ctrlWidget(host=self)
        self.ui.atlasLayout.addWidget(ctrl, 0, 0)
        self.atlas = ctrl
        

    def loadFileRequested(self, files):
        canvas = self.getElement('Canvas')
        if files is None:
            return

        for f in files:
            if f in self.files:   ## Do not allow loading the same file more than once
                item = self.files[f]
                item.show()
                continue
            
            item = canvas.addFile(f)
            if isinstance(item, list):
                item = item[0]
            self.items[item] = f
            self.files[f] = item
            try:
                item.timestamp = f.info()['__timestamp__']
            except:
                item.timestamp = None

            #self.loaded.append(f)
            
            ## load or guess user transform for this item
            if not item.hasUserTransform() and item.timestamp is not None:
                ## Record the timestamp for this file, see what is the most recent transformation to copy
                best = None
                for i2 in self.items:
                    if i2 is item:
                        continue
                    if i2.timestamp is None :
                        continue
                    if i2.timestamp < item.timestamp:
                        if best is None or i2.timestamp > best.timestamp:
                            best = i2
                            
                if best is None:
                    continue
                    
                trans = best.saveTransform()
                item.restoreTransform(trans)
                
            
        canvas.selectItem(item)
        canvas.autoRange()
    

    def itemMoved(self, canvas, item):
        """Save an item's transformation if the user has moved it. 
        This is saved in the 'userTransform' attribute; the original position data is not affected."""
        fh = self.items.get(item, None)
        if not hasattr(fh, 'setInfo'):
            fh = None
            
        try:
            item.storeUserTransform(fh)
        except Exception as ex:
            if len(ex.args) > 1 and ex.args[1] == 1:  ## this means the item has no file handle to store position
                return
            raise

    def getLoadedFiles(self):
        """Return a list of all file handles that have been loaded"""
        return self.items.values()
        
        
    def quit(self):
        self.files = None
        self.cells = None
        self.items = None
        self.ui.canvas.clear()
