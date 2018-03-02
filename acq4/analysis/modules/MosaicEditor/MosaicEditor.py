# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import glob
import json
import weakref
from collections import OrderedDict
import numpy as np
import scipy
import scipy.stats

import acq4.util.debug as debug
import acq4.pyqtgraph as pg
from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util import Qt
from .MosaicEditorTemplate import *
import acq4.util.DataManager as DataManager
import acq4.analysis.atlas as atlas
from acq4.util.Canvas.Canvas import Canvas
from acq4.util.Canvas import items
import acq4


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
    
    # Version number for save format.
    #   increment minor version number for backward-compatible changes
    #   increment major version number for backward-incompatible changes
    _saveVersion = (2, 0)
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.items = weakref.WeakKeyDictionary()
        self.files = weakref.WeakValueDictionary()
        
        self._addTypes = OrderedDict()

        self.ctrl = Qt.QWidget()
        self.ui = Ui_Form()
        self.ui.setupUi(self.ctrl)
        self.atlas = None
        self.canvas = Canvas(name='MosaicEditor')

        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            ('Mosaic', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('right',), 'size': (600, 100)}),
            ('Canvas', {'type': 'ctrl', 'object': self.canvas.ui.view, 'pos': ('bottom', 'Mosaic'), 'size': (600, 800)}),
            ('ItemList', {'type': 'ctrl', 'object': self.canvas.ui.canvasCtrlWidget, 'pos': ('right', 'Canvas'), 'size': (200, 400)}),
            ('ItemCtrl', {'type': 'ctrl', 'object': self.canvas.ui.canvasItemCtrl, 'pos': ('bottom', 'ItemList'), 'size': (200, 400)}),
        ])

        self.initializeElements()

        self.clear(ask=False)

        self.ui.fileLoader = self.getElement('File Loader', create=True)
        self.ui.fileLoader.ui.fileTree.hide()

        try:
            self.ui.fileLoader.setBaseClicked() # get the currently selected directory in the DataManager
        except:
            pass

        for a in atlas.listAtlases():
            self.ui.atlasCombo.addItem(a)
        
        # Add buttons to the canvas control panel    
        self.btnBox = Qt.QWidget()
        self.btnLayout = Qt.QGridLayout()
        self.btnLayout.setContentsMargins(0, 0, 0, 0)
        self.btnBox.setLayout(self.btnLayout)
        l = self.canvas.ui.gridLayout
        l.addWidget(self.btnBox, l.rowCount(), 0, 1, l.columnCount())

        self.addCombo = Qt.QComboBox()
        self.addCombo.currentIndexChanged.connect(self._addItemChanged)
        self.btnLayout.addWidget(self.addCombo, 0, 0, 1, 2)
        self.addCombo.addItem('Add item..')

        self.saveBtn = Qt.QPushButton("Save ...")
        self.saveBtn.clicked.connect(self.saveClicked)
        self.btnLayout.addWidget(self.saveBtn, 1, 0)

        self.clearBtn = Qt.QPushButton("Clear All")
        self.clearBtn.clicked.connect(lambda: self.clear(ask=True))
        self.btnLayout.addWidget(self.clearBtn, 1, 1)

        self.canvas.sigItemTransformChangeFinished.connect(self.itemMoved)
        self.ui.atlasCombo.currentIndexChanged.connect(self.atlasComboChanged)
        self.ui.normalizeBtn.clicked.connect(self.normalizeImages)
        self.ui.tileShadingBtn.clicked.connect(self.rescaleImages)
        self.ui.mosaicApplyScaleBtn.clicked.connect(self.updateScaling)
        self.ui.mosaicFlipLRBtn.clicked.connect(self.flipLR)
        self.ui.mosaicFlipUDBtn.clicked.connect(self.flipUD)

        self.imageMax = 0.0
        
        self.registerItemType(items.getItemType('GridCanvasItem'))
        self.registerItemType(items.getItemType('RulerCanvasItem'))
        self.registerItemType(items.getItemType('MarkersCanvasItem'))
        self.registerItemType(items.getItemType('CellCanvasItem'))
        self.registerItemType(items.getItemType('AtlasCanvasItem'))

    def registerItemType(self, itemclass, menuString=None):
        """Add an item type to the list of addable items. 
        """
        if menuString is None:
            menuString = itemclass.typeName()
        if itemclass.__name__ not in items.itemTypes():
            items.registerItemType(itemclass)
        self._addTypes[menuString] = itemclass.__name__
        self.addCombo.addItem(menuString)
            
    def _addItemChanged(self, index):
        # User requested to create and add a new item
        if index <= 0:
            return
        itemtype = self._addTypes[self.addCombo.currentText()]
        self.addCombo.setCurrentIndex(0)
        self.addItem(type=itemtype)

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
        obj = cls()
        ctrl = obj.ctrlWidget(host=self)
        self.ui.atlasLayout.addWidget(ctrl, 0, 0)
        self.atlas = ctrl

    def loadFileRequested(self, files):
        if files is None:
            return

        for f in files:
            if f.shortName().endswith('.mosaic'):
                self.loadStateFile(f.name())
                continue
                
            if f in self.files:   ## Do not allow loading the same file more than once
                item = self.files[f]
                item.show()  # just show the file; but do not load it
                continue
            
            if f.isFile():  # add specified files
                item = self.addFile(f)
            elif f.isDir():  # Directories are more complicated
                if self.dataModel.dirType(f) == 'Cell':  #  If it is a cell, just add the cell "Marker" to the plot
                    item = self.canvas.addFile(f)
                else:  # in all other directory types, look for MetaArray files
                    filesindir = glob.glob(f.name() + '/*.ma')
                    for fd in filesindir:  # add files in the directory (ma files: e.g., images, videos)
                        try:
                            fdh = DataManager.getFileHandle(fd) # open file to get handle.
                        except IOError:
                            continue # just skip file
                        item = self.addFile(fdh)
                    if len(filesindir) == 0:  # add protocol sequences
                        item = self.addFile(f)
        self.canvas.autoRange()

    def addFile(self, f, name=None, inheritTransform=True):
        """Load a file and add it to the canvas.
        
        The new item will inherit the user transform from the previous item
        (chronologocally) if it does not already have a user transform specified.
        """
        item = self.canvas.addFile(f, name=name)
        self.canvas.selectItem(item)
        
        if isinstance(item, list):
            item = item[0]
            
        self.items[item] = f
        self.files[f] = item
        try:
            item.timestamp = f.info()['__timestamp__']
        except:
            item.timestamp = None

        ## load or guess user transform for this item
        if inheritTransform and not item.hasUserTransform() and item.timestamp is not None:
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

            if best is not None:
                trans = best.saveTransform()
                item.restoreTransform(trans)
            
        return item

    def addItem(self, item=None, type=None, **kwds):
        """Add an item to the MosaicEditor canvas.

        May provide either *item* which is a CanvasItem or QGraphicsItem instance, or
        *type* which is a string specifying the type of item to create and add.
        """
        if isinstance(item, Qt.QGraphicsItem):
            return self.canvas.addGraphicsItem(item, **kwds)
        else:
            return self.canvas.addItem(item, type, **kwds)

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
        print(hm)
        #$meanImage = np.mean(self.selectedItems().asarray(), axis=0)
        n = 0
        self.imageMax = 0.0
        print('nsel: ', nsel)
        for i in range(nsel):
            try:
                meanImage = meanImage + np.array(self.canvas.selectedItems()[i].data)
                imagemax = np.amax(np.amax(meanImage, axis=1), axis=0)
                if imagemax > self.imageMax:
                    self.imageMax = imagemax
                n = n + 1
            except:
                print('image i = %d failed' % i)
                print('file name: ', self.canvas.selectedItems()[i].name)
                print('expected shape of nxm: ', nxm)
                print(' but got data shape: ', self.canvas.selectedItems()[i].data.shape)

        meanImage = meanImage/n # np.mean(meanImage[0:n], axis=0)
        filtwidth = np.floor(nxm[0]/10+1)
        blimg = scipy.ndimage.filters.gaussian_filter(meanImage, filtwidth, order = 0, mode='reflect')
        #pg.image(blimg)
        
        m = np.argmax(hm[0]) # returns the index of the max count
        print('m = ', m)
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
        print("MosaicEditor::self imageMax: ", self.imageMax)

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
        return list(self.items.values())

    def clear(self, ask=True):
        """Remove all loaded data and reset to the default state.
        
        If ask is True (and there are items loaded), then the user is prompted
        before clearing. If the user declines, then this method returns False.
        """
        if ask and len(self.items) > 0:
            response = Qt.QMessageBox.question(self.clearBtn, "Warning", "Really clear all items?", 
                Qt.QMessageBox.Ok|Qt.QMessageBox.Cancel)
            if response != Qt.QMessageBox.Ok:
                return False
            
        self.canvas.clear()
        self.items.clear()
        self.files.clear()
        self.lastSaveFile = None
        return True
        
    def saveState(self, relativeTo=None):
        """Return a serializable representation of the current state of the MosaicEditor.
        
        This includes the list of all items, their current visibility and
        parameters, and the view configuration.
        """
        items = list(self.canvas.items)
        items.sort(key=lambda i: i.zValue())

        return OrderedDict([
            ('contents', 'MosaicEditor_save'),
            ('version', self._saveVersion),
            ('rootPath', relativeTo.name() if relativeTo is not None else ''),
            ('items', [item.saveState(relativeTo=relativeTo) for item in items]),
            ('view', self.canvas.view.getState()),
        ])
        
    def saveStateFile(self, filename):
        dh = DataManager.getDirHandle(os.path.dirname(filename))
        state = self.saveState(relativeTo=dh)
        json.dump(state, open(filename, 'w'), indent=4, cls=Encoder)
        
    def restoreState(self, state, rootPath=None):
        if state.get('contents', None) != 'MosaicEditor_save':
            raise TypeError("This does not appear to be MosaicEditor save data.")
        if state['version'][0] > self._saveVersion[0]:
            raise TypeError("Save data has version %d.%d, but this MosaicEditor only supports up to version %d.x." % (state['version'][0], state['version'][1], self._saveVersion[0]))

        if not self.clear():
            return

        root = state['rootPath']
        if root == '':
            # data was stored with no root path; filenames should be absolute
            root = None
        else:
            # data was stored with no root path; filenames should be relative to the loaded file            
            root = DataManager.getHandle(rootPath)
            
        loadfail = []
        for itemState in state['items']:
            fname = itemState.get('filename')
            if fname is None:
                # create item from scratch and restore state
                itemtype = itemState.get('type')
                if itemtype not in items.itemTypes():
                    # warn the user later on that we could not load this item
                    loadfail.append((itemState.get('name'), 'Unknown item type "%s"' % itemtype))
                    continue
                item = self.addItem(type=itemtype, name=itemState['name'])
            else:
                # create item by loading file and restore state
                if root is None:
                    fh = DataManager.getHandle(fh)
                else:
                    fh = root[fname]
                item = self.addFile(fh, name=itemState['name'], inheritTransform=False)
            item.restoreState(itemState)

        self.canvas.view.setState(state['view'])
        if len(loadfail) > 0:
            msg = "\n".join(["%s: %s" % m for m in loadfail])
            raise Exception("Failed to load some items:\n%s" % msg)

    def loadStateFile(self, filename):
        state = json.load(open(filename, 'r'))
        self.restoreState(state, rootPath=os.path.dirname(filename))

    def saveClicked(self):
        base = self.ui.fileLoader.baseDir()
        if self.lastSaveFile is None:
            path = base.name()
        else:
            path = self.lastSaveFile
                
        filename = Qt.QFileDialog.getSaveFileName(None, "Save mosaic file", path, "Mosaic files (*.mosaic)")
        if filename == '':
            return
        if not filename.endswith('.mosaic'):
            filename += '.mosaic'
        self.lastSaveFile = filename
        
        self.saveStateFile(filename)

    def quit(self):
        self.files = None
        self.items = None
        self.canvas.clear()


class Encoder(json.JSONEncoder):
    """Used to clean up state for JSON export.
    """
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        
        return json.JSONEncoder.default(o)
