# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
from acq4.analysis.AnalysisModule import AnalysisModule
#from flowchart import *
import os
import glob
from collections import OrderedDict
import acq4.util.debug as debug
import numpy as np
import scipy
import scipy.stats
import acq4.pyqtgraph as pg

import weakref
#import FileLoader
#import DatabaseGui
#import FeedbackButton
from MosaicEditorTemplate import *
import acq4.util.DataManager as DataManager
import acq4.analysis.atlas as atlas


class MosaicEditor(AnalysisModule):
    """
    The Mosiac Editor allows the user to bring in multiple images onto
    a canvas, and manipulate the images, including adjusting contrast,
    position, and alpha.
    Images created in Acq4 that have position information will be
    represented according to their x,y positions (but not the z).

    Groups of images can be scaled together.
    An image stack can be "flattened" with different denoising methods
    - useful for a quick reconstruction of filled cells.
    Images can be compared against an atlas for reference, if the atlas
    data is loaded.
    This tool is useful for combining images taken at different positions
    with a camera or 2P imaging system.
    The resulting images may be saved as SVG or PNG files.
    Mosaic Editor makes extensive use of pyqtgraph Canvas methods.
    """
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrl = QtGui.QWidget()
        self.ui = Ui_Form()
        self.ui.setupUi(self.ctrl)
        self.atlas = None
        self.canvas = None # grab canvas information when loading files

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
        self.ui.normalizeBtn.clicked.connect(self.normalizeImages)
        self.ui.tileShadingBtn.clicked.connect(self.rescaleImages)
        self.ui.mosaicApplyScaleBtn.clicked.connect(self.updateScaling)
        self.ui.mosaicFlipLRBtn.clicked.connect(self.flipLR)
        self.ui.mosaicFlipUDBtn.clicked.connect(self.flipUD)

        self.imageMax = 0.0

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
        self.canvas = self.getElement('Canvas')
        if files is None:
            return

        for f in files:
            if f in self.files:   ## Do not allow loading the same file more than once
                item = self.files[f]
                item.show()  # just show the file; but do not load it
                continue
            
            if f.isFile():  # add specified files
                item = self.canvas.addFile(f)
            elif f.isDir():  # Directories are more complicated
                if self.dataModel.dirType(f) == 'Cell':  #  If it is a cell, just add the cell "Marker" to the plot
                # note: this breaks loading all images in Cell directory (need another way to do that)
                    item = self.canvas.addFile(f)
                else:  # in all other directory types, look for MetaArray files
                    filesindir = glob.glob(f.name() + '/*.ma')
                    for fd in filesindir:  # add files in the directory (ma files: e.g., images, videos)
                        try:
                            fdh = DataManager.getFileHandle(fd) # open file to get handle.
                        except IOError:
                            continue # just skip file
                        item = self.canvas.addFile(fdh)  # add it
                        self.amendFile(f, item)
                    if len(filesindir) == 0:  # add protocol sequences
                        item = self.canvas.addFile(f)
        self.canvas.selectItem(item)
        self.canvas.autoRange()

    def amendFile(self, f, item):
        """
        f must be a file loaded through canvas.
        Here we update the timestamp, the list of loaded files, and fix
        the transform if necessary
        """
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
                return

            trans = best.saveTransform()
            item.restoreTransform(trans)

    def rescaleImages(self):
        """
        Apply corrections to the images and rescale the data.
        This does the following:
        1. compute mean image over entire selected group
        2. smooth the mean image heavily.
        3. rescale the images and correct for field flatness from the average image
        4. apply the scale.
        Use the min/max mosaic button to readjust the display scale after this
        automatic operation if the scaling is not to your liking.
        """
        nsel =  len(self.canvas.selectedItems())
        if nsel == 0:
            return
       # print dir(self.selectedItems()[0].data)
        nxm = self.canvas.selectedItems()[0].data.shape
        meanImage = np.zeros((nxm[0], nxm[1]))
        nhistbins = 100
        # generate a histogram of the global levels in the image (all images selected)
        hm = np.histogram(np.dstack([x.data for x in self.canvas.selectedItems()]), nhistbins)
        print hm
        #$meanImage = np.mean(self.selectedItems().asarray(), axis=0)
        n = 0
        self.imageMax = 0.0
        print 'nsel: ', nsel
        for i in range(nsel):
            try:
                meanImage = meanImage + np.array(self.canvas.selectedItems()[i].data)
                imagemax = np.amax(np.amax(meanImage, axis=1), axis=0)
                if imagemax > self.imageMax:
                    self.imageMax = imagemax
                n = n + 1
            except:
                print 'image i = %d failed' % i
                print 'file name: ', self.canvas.selectedItems()[i].name
                print 'expected shape of nxm: ', nxm
                print ' but got data shape: ', self.canvas.selectedItems()[i].data.shape

        meanImage = meanImage/n # np.mean(meanImage[0:n], axis=0)
        filtwidth = np.floor(nxm[0]/10+1)
        blimg = scipy.ndimage.filters.gaussian_filter(meanImage, filtwidth, order = 0, mode='reflect')
        #pg.image(blimg)
        
        m = np.argmax(hm[0]) # returns the index of the max count
        print 'm = ', m
        # now rescale each individually
        # rescaling is done against the global histogram, to keep the gain constant.
        for i in range(nsel):
            d = np.array(self.canvas.selectedItems()[i].data)
#            hmd = np.histogram(d, 512) # return (count, bins)
            xh = d.shape # capture shape just in case it is not right (have data that is NOT !!)
            # flatten the illumination using the blimg average illumination pattern
            newImage = d # / blimg[0:xh[0], 0:xh[1]] # (d - imin)/(blimg - imin) # rescale image.
            hn = np.histogram(newImage, bins = hm[1]) # use bins from global image
            n = np.argmax(hn[0])
            newImage = (hm[1][m]/hn[1][n])*newImage # rescale to the global max.
            self.canvas.selectedItems()[i].updateImage(newImage)
         #   self.canvas.selectedItems()[i].levelRgn.setRegion([0, 2.0])
            self.canvas.selectedItems()[i].levelRgn.setRegion([0., self.imageMax])
        print "MosaicEditor::self imageMax: ", self.imageMax

    def normalizeImages(self):
        self.canvas.view.autoRange()

    def updateScaling(self):
        """
        Set all the selected images to have the scaling in the editor bar (absolute values)
        """
        nsel =  len(self.canvas.selectedItems())
        if nsel == 0:
            return
        for i in range(nsel):
            self.canvas.selectedItems()[i].levelRgn.setRegion([self.ui.mosaicDisplayMin.value(),
                                                               self.ui.mosaicDisplayMax.value()])

    def flipUD(self):
        """
        flip each image array up/down, in place. Do not change position.
        Note: arrays are rotated, so use lr to do ud, etc.
        """
        nsel =  len(self.canvas.selectedItems())
        if nsel == 0:
            return
        for i in range(nsel):
            self.canvas.selectedItems()[i].data = np.fliplr(self.canvas.selectedItems()[i].data)
            self.canvas.selectedItems()[i].graphicsItem().updateImage(self.canvas.selectedItems()[i].data)
           # print dir(self.canvas.selectedItems()[i])

    def flipLR(self):
        """
        Flip each image array left/right, in place. Do not change position.
        """
        nsel =  len(self.canvas.selectedItems())
        if nsel == 0:
            return
        for i in range(nsel):
            self.canvas.selectedItems()[i].data = np.flipud(self.canvas.selectedItems()[i].data)
            self.canvas.selectedItems()[i].graphicsItem().updateImage(self.canvas.selectedItems()[i].data)

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
