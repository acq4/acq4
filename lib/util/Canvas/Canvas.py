# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import sys, os
    md = os.path.dirname(os.path.abspath(__file__))
    sys.path = [os.path.dirname(md)] + sys.path
    #print md
    
from CanvasTemplate import *
from pyqtgraph import TransformGuiTemplate
from pyqtgraph.GraphicsView import GraphicsView
import pyqtgraph.graphicsItems as graphicsItems
from pyqtgraph.PlotWidget import PlotWidget
from pyqtgraph import widgets
from PyQt4 import QtGui, QtCore, QtSvg
import DataManager
import numpy as np
import debug
import pyqtgraph as pg
import scipy.ndimage as ndimage
import weakref
from CanvasManager import CanvasManager

class Canvas(QtGui.QWidget):
    
    sigSelectionChanged = QtCore.Signal(object, object)
    sigItemTransformChanged = QtCore.Signal(object, object)
    sigItemTransformChangeFinished = QtCore.Signal(object, object)
    
    def __init__(self, parent=None, allowTransforms=True, hideCtrl=False, name=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.view = self.ui.view
        self.itemList = self.ui.itemList
        self.itemList.setSelectionMode(self.itemList.ExtendedSelection)
        self.allowTransforms = allowTransforms
        self.multiSelectBox = SelectBox()
        self.scene().addItem(self.multiSelectBox)
        self.multiSelectBox.hide()
        self.multiSelectBox.setZValue(1e6)
        self.ui.mirrorImagesBtn.hide()
        self.ui.resetTransformsBtn.hide()
        
        self.redirect = None  ## which canvas to redirect items to
        self.items = {}
        
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
        self.grid = graphicsItems.GridItem(self.view)
        self.addItem(self.grid, name='Grid', movable=False)
        
        self.hideBtn = QtGui.QPushButton('>', self)
        self.hideBtn.setFixedWidth(20)
        self.hideBtn.setFixedHeight(20)
        self.ctrlSize = 200
        #self.connect(self.hideBtn, QtCore.SIGNAL('clicked()'), self.hideBtnClicked)
        self.hideBtn.clicked.connect(self.hideBtnClicked)
        #self.connect(self.ui.splitter, QtCore.SIGNAL('splitterMoved(int, int)'), self.splitterMoved)
        self.ui.splitter.splitterMoved.connect(self.splitterMoved)
        
        #self.connect(self.ui.itemList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.treeItemChanged)
        self.ui.itemList.itemChanged.connect(self.treeItemChanged)
        #self.connect(self.ui.itemList, QtCore.SIGNAL('itemMoved'), self.treeItemMoved)
        self.ui.itemList.sigItemMoved.connect(self.treeItemMoved)
        #self.connect(self.ui.itemList, QtCore.SIGNAL('itemSelectionChanged()'), self.treeItemSelected)
        self.ui.itemList.itemSelectionChanged.connect(self.treeItemSelected)
        #self.connect(self.ui.autoRangeBtn, QtCore.SIGNAL('clicked()'), self.autoRangeClicked)
        self.ui.autoRangeBtn.clicked.connect(self.autoRangeClicked)
        self.ui.storeSvgBtn.clicked.connect(self.storeSvg)
        self.ui.storePngBtn.clicked.connect(self.storePng)
        self.ui.redirectCheck.toggled.connect(self.updateRedirect)
        self.ui.redirectCombo.currentIndexChanged.connect(self.updateRedirect)
        self.multiSelectBox.sigRegionChanged.connect(self.multiSelectBoxChanged)
        self.multiSelectBox.sigRegionChangeFinished.connect(self.multiSelectBoxChangeFinished)
        self.ui.mirrorImagesBtn.clicked.connect(self.mirrorImagesClicked)
        self.ui.resetTransformsBtn.clicked.connect(self.resetTransformsClicked)
        
        self.resizeEvent()
        if hideCtrl:
            self.hideBtnClicked()
            
        if name is not None:
            self.registeredName = CanvasManager.instance().registerCanvas(self, name)
            self.ui.redirectCombo.setHostName(self.registeredName)

    def storeSvg(self):
        self.ui.view.writeSvg()

    def storePng(self):
        self.ui.view.writePng()

    def splitterMoved(self):
        self.resizeEvent()

    def hideBtnClicked(self):
        ctrlSize = self.ui.splitter.sizes()[1]
        if ctrlSize == 0:
            cs = self.ctrlSize
            w = self.ui.splitter.size().width()
            if cs > w:
                cs = w - 20
            self.ui.splitter.setSizes([w-cs, cs])
            self.hideBtn.setText('>')
        else:
            self.ctrlSize = ctrlSize
            self.ui.splitter.setSizes([100, 0])
            self.hideBtn.setText('<')
        self.resizeEvent()

    def autoRangeClicked(self):
        items = []
        for i in range(self.itemList.topLevelItemCount()):
            name = self.itemList.topLevelItem(i).name
            item = self.items[name].item
            if item.isVisible() and item is not self.grid:
                items.append(item)
        if len(items) < 1:
            return
        bounds = items[0].sceneBoundingRect()
        if len(items) > 1:
            for i in items[1:]:
                bounds |= i.sceneBoundingRect()
        self.view.setRange(bounds)

    def resizeEvent(self, ev=None):
        if ev is not None:
            QtGui.QWidget.resizeEvent(self, ev)
        self.hideBtn.move(self.view.size().width() - self.hideBtn.width(), 0)

    
    def updateRedirect(self, *args):
        ### Decide whether/where to redirect items and make it so
        cname = str(self.ui.redirectCombo.currentText())
        man = CanvasManager.instance()
        if self.ui.redirectCheck.isChecked() and cname != '':
            redirect = man.getCanvas(cname)
        else:
            redirect = None
            
        if self.redirect is redirect:
            return
            
        self.redirect = redirect
        if redirect is None:
            self.reclaimItems()
        else:
            self.redirectItems(redirect)

    
    def redirectItems(self, canvas):
        for i in self.items.itervalues():
            li = i.listItem
            parent = li.parent()
            if parent is None:
                tree = li.treeWidget()
                if tree is None:
                    print "Skipping item", i, i.name
                    continue
                tree.removeTopLevelItem(li)
            else:
                parent.removeChild(li)
            canvas._addCanvasItem(i)
            

    def reclaimItems(self):
        for i in self.items.itervalues():
            self._addCanvasItem(i)

    def treeItemChanged(self, item, col):
        gi = self.items.get(item.name, None)
        if gi is None:
            return
        if item.checkState(0) == QtCore.Qt.Checked:
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, QtCore.Qt.Checked)
            gi.show()
        else:
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, QtCore.Qt.Unchecked)
            gi.hide()

    def treeItemMoved(self, item, parent, index):
        ##Item moved in tree; update its Z value
        zvals = [i.item.zValue() for i in self.items.itervalues()]
        zvals.sort(reverse=True)
        
        for i in range(self.itemList.topLevelItemCount()):
            item = self.itemList.topLevelItem(i)
            gi = self.items[item.name]
            if gi.item.zValue() != zvals[i]:
                gi.item.setZValue(zvals[i])
        
        #if self.itemList.topLevelItemCount() < 2:
            #return
        #name = item.name
        #gi = self.items[name]
        #if index == 0:   
            #next = self.itemList.topLevelItem(1)
            #z = self.items[next.name].zValue()+1
        #else:
            #prev = self.itemList.topLevelItem(index-1)
            #z = self.items[prev.name].zValue()-1
        #gi.setZValue(z)

    def treeItemSelected(self):
        sel = self.itemList.selectedItems()
        sel = [self.items[item.name] for item in sel]
        if len(sel) == 0:
            #self.selectWidget.hide()
            return
        for i in self.items.itervalues():
            i.ctrlWidget().hide()
            
        if len(sel)==1:
            item = sel[0]
            item.ctrlWidget().show()
            self.multiSelectBox.hide()
            self.ui.mirrorImagesBtn.hide()
            self.ui.resetTransformsBtn.hide()
            
        elif len(sel) > 1:
            self.showMultiSelectBox()
        
        #if item.isMovable():
            #self.selectBox.setPos(item.item.pos())
            #self.selectBox.setSize(item.item.sceneBoundingRect().size())
            #self.selectBox.show()
        #else:
            #self.selectBox.hide()
        
        #self.emit(QtCore.SIGNAL('itemSelected'), self, item)
        self.sigSelectionChanged.emit(self, sel)
        
    def showMultiSelectBox(self):
        items = self.itemList.selectedItems()
        rect = items[0].item.item.sceneBoundingRect()
        for i in items:
            if not i.item.isMovable():  ## all items in selection must be movable
                return
            br = i.item.item.sceneBoundingRect()
            rect = rect|br
            
        self.multiSelectBox.blockSignals(True)
        self.multiSelectBox.setPos([rect.x(), rect.y()])
        self.multiSelectBox.setSize(rect.size())
        self.multiSelectBox.setAngle(0)
        self.multiSelectBox.blockSignals(False)
        
        self.multiSelectBox.show()
        self.ui.mirrorImagesBtn.show()
        self.ui.resetTransformsBtn.show()
        #self.multiSelectBoxBase = self.multiSelectBox.getState().copy()
    
    def mirrorImagesClicked(self):
        items = self.itemList.selectedItems()
        for i in items:
            ci = i.item
            ci.transformGui.mirrorImageCheck.toggle()
        self.showMultiSelectBox()
            
    def resetTransformsClicked(self):
        items = self.itemList.selectedItems()
        for i in items:
            i.item.resetTransformClicked()
        self.showMultiSelectBox()
        
    def multiSelectBoxChanged(self):
        self.multiSelectBoxMoved()
        
    def multiSelectBoxChangeFinished(self):
        for ti in self.itemList.selectedItems():
            ci = ti.item
            ci.applyTemporaryTransform()
            ci.sigTransformChangeFinished.emit(ci)
        
    def multiSelectBoxMoved(self):
        transform = self.multiSelectBox.getGlobalTransform()
        
        for ti in self.itemList.selectedItems():
            ci = ti.item
            ci.setTemporaryTransform(transform)
            ci.sigTransformChanged.emit(ci)
        
        
    def selectedItem(self):
        sel = self.itemList.selectedItems()
        if sel is None or len(sel) < 1:
            return
        return self.items.get(sel[0].name, None)

    def selectItem(self, item):
        li = item.listItem
        #li = self.getListItem(item.name())
        #print "select", li
        self.itemList.setCurrentItem(li)


    def addItem(self, item, **opts):
        """Add a new GraphicsItem to the scene at pos.
        Common options are name, pos, scale, and z
        """
        citem = CanvasItem(self, item, **opts)
        self._addCanvasItem(citem)
        return citem
            
    def addImage(self, img, **opts):
        #if isinstance(img, DataManager.FileHandle):
            #fh = img
            #img = img.read()
            #if 'name' not in opts:
                #opts['name'] = fh.shortName()

            #if 'imagePosition' in fh.info():
                #opts['scale'] = fh.info()['pixelSize']
                #opts['pos'] = fh.info()['imagePosition']
            #else:
                #info = img._info[-1]
                #opts['scale'] = info['pixelSize']
                #opts['pos'] = info['imagePosition']

        #if img.ndim == 3:
            #img = img[0]
            
        #item = graphicsItems.ImageItem(img)
        citem = ImageCanvasItem(self, img, **opts)
        self._addCanvasItem(citem)
        return citem
    
    ### Make addScan and addImage go away entirely, plox.
    def addScan(self, dirHandle, **opts):
        """Returns a list of ScanCanvasItems."""
        
        if 'sequenceParams' in dirHandle.info():
            dirs = [dirHandle[d] for d in dirHandle.subDirs()]
        else:
            dirs = [dirHandle]
            
        if 'separateParams' not in opts:
            separateParams = False
        else:
            separateParams = opts['separateParams']
            del(opts['separateParams'])
            
        
        ### check for sequence parameters (besides targets) so that we can separate them out into individual Scans
        paramKeys = []
        params = dirHandle.info()['protocol']['params']
        if len(params) > 1 and separateParams==True:
            for i in range(len(params)):
                k = (params[i][0], params[i][1])
                if k != ('Scanner', 'targets'):
                    paramKeys.append(k)
            
        if 'name' not in opts:
            opts['name'] = dirHandle.shortName()
            

            
        if len(paramKeys) < 1:    
            pts = []
            for d in dirs: #d is a directory handle
                #d = dh[d]
                if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    pos = d.info()['Scanner']['position']
                    if 'spotSize' in d.info()['Scanner']:
                        size = d.info()['Scanner']['spotSize']
                    else:
                        size = self.defaultSize
                    pts.append({'pos': pos, 'size': size, 'data': d})
            
            item = graphicsItems.ScatterPlotItem(pts, pxMode=False)
            citem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            self._addCanvasItem(citem)
            return [citem]
        else:
            pts = {}
            for d in dirs:
                k = d.info()[paramKeys[0]]
                if len(pts) < k+1:
                    pts[k] = []
                if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    pos = d.info()['Scanner']['position']
                    if 'spotSize' in d.info()['Scanner']:
                        size = d.info()['Scanner']['spotSize']
                    else:
                        size = self.defaultSize
                    pts[k].append({'pos': pos, 'size': size, 'data': d})
            spots = []
            for k in pts.keys():
                spots.extend(pts[k])
            item = graphicsItems.ScatterPlotItem(spots=spots, pxMode=False)
            parentCitem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            self._addCanvasItem(parentCitem)
            scans = []
            for k in pts.keys():
                opts['name'] = paramKeys[0][0] + '_%03d' %k
                item = graphicsItems.ScatterPlotItem(spots=pts[k], pxMode=False)
                citem = ScanCanvasItem(self, item, handle = dirHandle, parent=parentCitem, **opts)
                self._addCanvasItem(citem)
                #scans[opts['name']] = citem
                scans.append(citem)
            return scans
                
                
        
    def addFile(self, fh, **opts):
        if fh.isFile():
            if fh.shortName()[-4:] == '.svg':
                return self.addSvg(fh, **opts)
            else:
                return self.addImage(fh, **opts)
        else:
            return self.addScan(fh, **opts)

    def addMarker(self, **opts):
        citem = MarkerCanvasItem(self, **opts)
        self._addCanvasItem(citem)
        return citem

    def addSvg(self, fh, **opts):
        item = QtSvg.QGraphicsSvgItem(fh.name())
        return self.addItem(item, handle=fh, **opts)


    def _addCanvasItem(self, citem):
        """Obligatory function call for any items added to the canvas."""
        
        if self.redirect is not None:
            name = self.redirect._addCanvasItem(citem)
            self.items[name] = citem
            return name


        if not self.allowTransforms:
            citem.setMovable(False)

        #self.connect(citem, QtCore.SIGNAL('transformChanged'), self.itemTransformChanged)
        citem.sigTransformChanged.connect(self.itemTransformChanged)
        #self.connect(citem, QtCore.SIGNAL('transformChangeFinished'), self.itemTransformChangeFinished)
        citem.sigTransformChangeFinished.connect(self.itemTransformChangeFinished)
        citem.sigVisibilityChanged.connect(self.itemVisibilityChanged)

        item = citem.item
        name = citem.opts['name']
        
        self.view.scene().addItem(item)
        
        ## Autoscale to fit the first item added (not including the grid).
        if len(self.items) == 1:
            self.view.setRange(item.mapRectToScene(item.boundingRect()))
            
        #if isinstance(name, basestring):
            #name = [name]
            
        if name is None:
            name = 'item'
           
        newname = name
        
        ## If name already exists, append a number to the end
        c=0
        while newname in self.items:
            c += 1
            newname = name + '_%03d' %c
        name = newname
            
        ## find parent and add item to tree
        #currentNode = self.itemList.invisibleRootItem()
        insertLocation = 0
        #print "Inserting node:", name
        
        
        ## Add node to tree, allowing nested nodes
        #for n in name:
            #nextnode = None
            #for x in range(currentNode.childCount()):
                #ch = currentNode.child(x)
                #if hasattr(ch, 'name'):    ## check Z-value of current item to determine insert location
                    #zval = self.items[ch.name].zValue()
                    #if zval > z:
                        ##print "  ->", x
                        #insertLocation = x+1
                #if n == ch.text(0):
                    #nextnode = ch
                    #break
            #if nextnode is None:  ## If name doesn't exist, create it
                #nextnode = QtGui.QTreeWidgetItem([n])
                #nextnode.setFlags((nextnode.flags() | QtCore.Qt.ItemIsUserCheckable) & ~QtCore.Qt.ItemIsDropEnabled)
                #nextnode.setCheckState(0, QtCore.Qt.Checked)
                ### Add node to correct position in list by Z-value
                ##print "  ==>", insertLocation
                #currentNode.insertChild(insertLocation, nextnode)
                
                #if n == name[-1]:   ## This is the leaf; add some extra properties.
                    #nextnode.name = name
                
                #if n == name[0]:   ## This is the root; make the item movable
                    #nextnode.setFlags(nextnode.flags() | QtCore.Qt.ItemIsDragEnabled)
                #else:
                    #nextnode.setFlags(nextnode.flags() & ~QtCore.Qt.ItemIsDragEnabled)
                    
            #currentNode = nextnode
            
        z = citem.zValue()
        if z is None:
            zvals = [i.zValue() for i in self.items.itervalues()]
            if len(zvals) == 0:
                z = 0
            else:
                z = max(zvals)+10
            citem.setZValue(z)
            
        root = self.itemList.invisibleRootItem()
        for i in range(root.childCount()):
            ch = root.child(i)
            zval = self.items[ch.name].item.zValue()
            if zval < z:
                #print zval, "<", z
                insertLocation = i
                break
            else:
                insertLocation = i+1
                #print zval, ">", z
                
        #print name, insertLocation, z
        node = QtGui.QTreeWidgetItem([name])
        node.setFlags((node.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsDragEnabled) & ~QtCore.Qt.ItemIsDropEnabled)
        if citem.opts['visible']:
            node.setCheckState(0, QtCore.Qt.Checked)
        else:
            node.setCheckState(0, QtCore.Qt.Unchecked)
        
        node.name = name
        if citem.opts['parent'] != None:
            ## insertLocation is incorrect in this case
            citem.opts['parent'].listItem.insertChild(insertLocation, node)
        else:    
            root.insertChild(insertLocation, node)
        
        #citem = CanvasItem(self, name, item)
        citem.name = name
        citem.listItem = node
        node.item = citem
        self.items[name] = citem

        ctrl = citem.ctrlWidget()
        ctrl.hide()
        self.ui.ctrlLayout.addWidget(ctrl)

        #self.items[tuple(name)] = item
        return name
        
    def itemVisibilityChanged(self, item):
        listItem = item.listItem
        checked = listItem.checkState(0) == QtCore.Qt.Checked
        vis = item.isVisible()
        if vis != checked:
            if vis:
                listItem.setCheckState(0, QtCore.Qt.Checked)
            else:
                listItem.setCheckState(0, QtCore.Qt.Unchecked)

    def removeItem(self, item):
        if isinstance(item, CanvasItem):
            self.view.scene().removeItem(item.item)
            self.itemList.removeTopLevelItem(item.listItem)
        else:
            self.view.scene().removeItem(item)
        
        ## disconnect signals, remove from list, etc..
        
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items
        
    def getListItem(self, name):
        return self.items[name]
        
    def scene(self):
        return self.view.scene()
        
    def itemTransformChanged(self, item):
        #self.emit(QtCore.SIGNAL('itemTransformChanged'), self, item)
        self.sigItemTransformChanged.emit(self, item)
    
    def itemTransformChangeFinished(self, item):
        #self.emit(QtCore.SIGNAL('itemTransformChangeFinished'), self, item)
        self.sigItemTransformChangeFinished.emit(self, item)
        


class SelectBox(widgets.ROI):
    def __init__(self, scalable=False):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        widgets.ROI.__init__(self, [0,0], [1,1])
        center = [0.5, 0.5]
            
        if scalable:
            self.addScaleHandle([1, 1], center, lockAspect=True)
            self.addScaleHandle([0, 0], center, lockAspect=True)
        self.addRotateHandle([0, 1], center)
        self.addRotateHandle([1, 0], center)


class CanvasItem(QtCore.QObject):
    
    sigResetUserTransform = QtCore.Signal(object)
    sigTransformChangeFinished = QtCore.Signal(object)
    sigTransformChanged = QtCore.Signal(object)
    
    """CanvasItem takes care of managing an item's state--alpha, visibility, z-value, transformations, etc. and
    provides a control widget"""
    
    sigVisibilityChanged = QtCore.Signal(object)
    transformCopyBuffer = None
    
    def __init__(self, canvas, item, **opts):
        defOpts = {'name': None, 'z': None, 'movable': True, 'scalable': False, 'handle': None, 'visible': True, 'parent':None} #'pos': [0,0], 'scale': [1,1], 'angle':0,
        defOpts.update(opts)
        self.opts = defOpts
        self.selected = False
        
        QtCore.QObject.__init__(self)
        self.canvas = canvas
        self.item = item
        
        z = self.opts['z']
        if z is not None:
            item.setZValue(z)

        self.ctrl = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.layout.setSpacing(0)
        self.ctrl.setLayout(self.layout)
        
        self.alphaLabel = QtGui.QLabel("Alpha")
        self.alphaSlider = QtGui.QSlider()
        self.alphaSlider.setMaximum(1023)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setValue(1023)
        self.layout.addWidget(self.alphaLabel, 0, 0)
        self.layout.addWidget(self.alphaSlider, 0, 1)
        self.resetTransformBtn = QtGui.QPushButton('Reset Transform')
        self.copyBtn = QtGui.QPushButton('Copy')
        self.pasteBtn = QtGui.QPushButton('Paste')
        self.layout.addWidget(self.resetTransformBtn, 1, 0, 1, 2)
        self.layout.addWidget(self.copyBtn, 2, 0, 1, 1)
        self.layout.addWidget(self.pasteBtn, 2, 1, 1, 1)
        self.transformWidget = QtGui.QWidget()
        self.transformGui = TransformGuiTemplate.Ui_Form()
        self.transformGui.setupUi(self.transformWidget)
        self.layout.addWidget(self.transformWidget, 3, 0, 1, 2)
        
        self.alphaSlider.valueChanged.connect(self.alphaChanged)
        self.alphaSlider.sliderPressed.connect(self.alphaPressed)
        self.alphaSlider.sliderReleased.connect(self.alphaReleased)
        self.canvas.sigSelectionChanged.connect(self.selectionChanged)
        self.resetTransformBtn.clicked.connect(self.resetTransformClicked)
        self.copyBtn.clicked.connect(self.copyClicked)
        self.pasteBtn.clicked.connect(self.pasteClicked)
        self.transformGui.mirrorImageCheck.stateChanged.connect(self.mirrorImage)
        
        if 'transform' in self.opts:
            self.baseTransform = self.opts['transform']
        else:
            self.baseTransform = pg.Transform()
            if 'pos' in self.opts:
                self.baseTransform.translate(self.opts['pos'])
            if 'angle' in self.opts:
                self.baseTransform.rotate(self.opts['angle'])
            if 'scale' in self.opts:
                self.baseTransform.scale(self.opts['scale'])

        ## create selection box (only visible when selected)
        tr = self.baseTransform.saveState()
        if 'scalable' not in opts and tr['scale'] == (1,1):
            self.opts['scalable'] = True
        self.selectBox = SelectBox(scalable=self.opts['scalable'])
        self.canvas.scene().addItem(self.selectBox)
        self.selectBox.hide()
        self.selectBox.setZValue(1e6)
        self.selectBox.sigRegionChanged.connect(self.selectBoxChanged)  ## calls selectBoxMoved
        self.selectBox.sigRegionChangeFinished.connect(self.selectBoxChangeFinished)

        ## set up the transformations that will be applied to the item
        ## (It is not safe to use item.setTransform, since the item might count on that not changing)
        self.itemRotation = QtGui.QGraphicsRotation()
        self.itemScale = QtGui.QGraphicsScale()
        self.item.setTransformations([self.itemRotation, self.itemScale])
        
        self.tempTransform = pg.Transform() ## holds the additional transform that happens during a move - gets added to the userTransform when move is done.
        self.userTransform = pg.Transform() ## stores the total transform of the object
        self.resetUserTransform() 
        self.selectBoxBase = self.selectBox.getState().copy()
        
        ## reload user transform from disk if possible
        if self.opts['handle'] is not None:
            trans = self.opts['handle'].info().get('userTransform', None)
            if trans is not None:
                self.restoreTransform(trans)
                
        #print "Created canvas item", self
        #print "  base:", self.baseTransform
        #print "  user:", self.userTransform
        #print "  temp:", self.tempTransform
        #print "  bounds:", self.item.sceneBoundingRect()

    def graphicsItem(self):
        return self.item

    #def name(self):
        #return self.opts['name']
    def handle(self):
        """Return the file handle for this item, if any exists."""
        return self.opts['handle']
                             
    def copyClicked(self):
        CanvasItem.transformCopyBuffer = self.saveTransform()
        
    def pasteClicked(self):
        t = CanvasItem.transformCopyBuffer
        if t is None:
            return
        else:
            self.restoreTransform(t)
            
    def mirrorImage(self, state):
        if not self.isMovable():
            return
        
        flip = self.transformGui.mirrorImageCheck.isChecked()
        tr = self.userTransform.saveState()
        
        if flip:
            if tr['scale'][0] < 0 or tr['scale'][1] < 0:
                return
            else:
                self.userTransform.setScale([-tr['scale'][0], tr['scale'][1]])
                self.userTransform.setTranslate([-tr['pos'][0], tr['pos'][1]])
                self.userTransform.setRotate(-tr['angle'])
                self.updateTransform()
                self.selectBoxFromUser()
                return
        elif not flip:
            if tr['scale'][0] > 0 and tr['scale'][1] > 0:
                return
            else:
                self.userTransform.setScale([-tr['scale'][0], tr['scale'][1]])
                self.userTransform.setTranslate([-tr['pos'][0], tr['pos'][1]])
                self.userTransform.setRotate(-tr['angle'])
                self.updateTransform()
                self.selectBoxFromUser()
                return
                
    def hasUserTransform(self):
        #print self.userRotate, self.userTranslate
        return not self.userTransform.isIdentity()

    def ctrlWidget(self):
        return self.ctrl
        
    def alphaChanged(self, val):
        alpha = val / 1023.
        self.item.setOpacity(alpha)
        
    def isMovable(self):
        return self.opts['movable']
        
    def setMovable(self, m):
        self.opts['movable'] = m
        
    def selectBoxMoved(self):
        """The selection box has moved; get its transformation information and pass to the graphics item"""
        #translate, rotate = self.selectBox.getGlobalTransform(relativeTo=self.selectBoxBase)
        
        #self.userTranslate = translate
        #self.userRotate = rotate
        
        #self.updateTransform()
        
        self.userTransform = self.selectBox.getGlobalTransform(relativeTo=self.selectBoxBase)
        self.updateTransform()
        
        
        #st = self.selectBox.getState()
        
        #bPos1 = pg.Point(self.selectBoxBase['pos'])
        #bPos2 = pg.Point(st['pos'])
        
        ### How far the box has moved from its starting position
        #trans = bPos2 - bPos1
        
        ### rotation
        #ang = -st['angle'] * 180. / 3.14159265358
        #rot = QtGui.QTransform()
        #rot.rotate(ang)

        ### We need to come up with a universal transformation--one that can be applied to other objects 
        ### such that all maintain alignment. 
        ### More specifically, we need to turn the selection box's position and angle into
        ### a rotation _around the origin_ and a translation.
        
        ### Approach is:
        ### 1. Call the center of the item's coord. system p0
        ### 2. Rotate p0 by ang around the global origin; call this point p1
        ### 3. The point where the item's origin will end up ultimately is p2
        ### 4. The translation we are looking for is p2 - (p1-p0) - 

        #p0 = pg.Point(self.basePos)

        ### base position, rotated
        #p1 = rot.map(p0)
        
        ### find final location of item:
        ### item pos relative to box
        #relPos = p0 - bPos1
        ##print relPos, p0, bPos1
        
        ### rotate
        #relPos2 = rot.map(relPos)
        
        ### final location of item
        #p2 = relPos2 + trans
        
        ### translation left over
        #t2 = p2 - (p1-p0) - relPos
        ##print trans, p2, p1, t2
        
        #self.userTranslate = [t2.x(), t2.y()]
        #self.userRotate = st['angle']
        
        #self.updateTransform()
    def setTemporaryTransform(self, transform):
        self.tempTransform = transform
        self.updateTransform()
    
    def applyTemporaryTransform(self):
        ##### THIS IS WHAT I NEED TO FIX!
        #"""Combines the temporary transform with the userTransform, and sets the userTransform"""
        #transform = QtGui.QTransform()
        ##transform.translate(*self.tempTranslate)
        #transform.rotate(-self.tempRotate)
        #transform.translate(*self.tempTranslate)
        #translate = transform.map(0.0, 0.0)
        #print "Old userTransform: ", self.userTranslate, self.userRotate
        #print "    tempTransform: ", translate, self.tempRotate
        
        #self.userTranslate = self.userTranslate + self.tempTranslate
        #self.userRotate += self.tempRotate
        #print "New userTransform: ", self.userTranslate, self.userRotate
        #self.resetTemporaryTransform()
        #self.selectBoxFromUser()
        st = self.userTransform.saveState()
        
        self.userTransform = self.userTransform * self.tempTransform ## order is important!
        
        ### matrix multiplication affects the scale factors, need to reset
        if st['scale'][0] < 0 or st['scale'][1] < 0:
            nst = self.userTransform.saveState()
            self.userTransform.setScale([-nst['scale'][0], -nst['scale'][1]])
        
        self.resetTemporaryTransform()
        self.selectBoxFromUser()
        self.selectBoxChangeFinished()
        #self.updateTransform()
    
    def resetTemporaryTransform(self):
        self.tempTransform = pg.Transform()
        self.updateTransform()
        
    def transform(self): 
        return self.item.transform()

    def updateTransform(self):
        """Regenerate the item position from the base and user transform"""
        ## Ideally we want to apply transformations in this order: 
        ##    scale * baseTranslate * userRotate * userTranslate
        ## HOWEVER: transformations are actually applied like this:
        ##    scale * rotate * translate
        ## So we just need to do some rearranging:
        ##    scale * userRotate * (userRotate^-1 * baseTranslate * userRotate) * userTranslate
        
        #p1 = self.baseTranform.
        #transform = QtGui.QTransform()
        #transform.translate(*self.tempTranslate)
        #transform.rotate(-self.tempRotate)
        #transform.translate(*self.userTranslate)
        #transform.rotate(-self.userRotate)
        #print "Temp: ", self.tempTransform.matrix()
        #print "User: ", self.userTransform.matrix()
        #print "Base: ", self.baseTransform.matrix()
        
        
        
        transform = self.baseTransform * self.userTransform *self.tempTransform## order is important
        #print "Transform: ", transform.matrix()
            
        s = transform.saveState()
        self.item.setPos(*s['pos'])
        
        self.itemRotation.setAngle(s['angle'])
        self.itemScale.setXScale(s['scale'][0])
        self.itemScale.setYScale(s['scale'][1])
        
        self.displayTransform(transform)
        
    def displayTransform(self, transform):
        """Updates transform numbers in the ctrl widget."""
        
        tr = transform.saveState()
        
        self.transformGui.translateLabel.setText("Translate: (%f, %f)" %(tr['pos'][0], tr['pos'][1]))
        self.transformGui.rotateLabel.setText("Rotate: %f degrees" %tr['angle'])
        self.transformGui.scaleLabel.setText("Scale: (%f, %f)" %(tr['scale'][0], tr['scale'][1]))
        #self.transformGui.mirrorImageCheck.setChecked(False)
        #if tr['scale'][0] < 0:
        #    self.transformGui.mirrorImageCheck.setChecked(True)

        

    def resetUserTransform(self):
        #self.userRotate = 0
        #self.userTranslate = pg.Point(0,0)
        self.userTransform.reset()
        self.updateTransform()
        
        self.selectBox.blockSignals(True)
        self.selectBoxToItem()
        self.selectBox.blockSignals(False)
        self.sigTransformChanged.emit(self)
        self.sigTransformChangeFinished.emit(self)
        
    def resetTransformClicked(self):
        self.resetUserTransform()
        self.sigResetUserTransform.emit(self)
        
    def restoreTransform(self, tr):
        try:
            #self.userTranslate = pg.Point(tr['trans'])
            #self.userRotate = tr['rot']
            self.userTransform = pg.Transform(tr)
            self.updateTransform()
            self.selectBoxFromUser() ## move select box to match
            self.sigTransformChanged.emit(self)
            self.sigTransformChangeFinished.emit(self)
        except:
            #self.userTranslate = pg.Point([0,0])
            #self.userRotate = 0
            self.userTransform = pg.Transform()
            debug.printExc("Failed to load transform:")
        #print "set transform", self, self.userTranslate
        
    def saveTransform(self):
        #print "save transform", self, self.userTranslate
        #return {'trans': list(self.userTranslate), 'rot': self.userRotate}
        return self.userTransform.saveState()
    
    def selectBoxFromUser(self):
        """Move the selection box to match the current userTransform"""
        ## user transform
        #trans = QtGui.QTransform()
        #trans.translate(*self.userTranslate)
        #trans.rotate(-self.userRotate)
        
        #x2, y2 = trans.map(*self.selectBoxBase['pos'])
        
        self.selectBox.blockSignals(True)
        self.selectBox.setState(self.selectBoxBase)
        self.selectBox.applyGlobalTransform(self.userTransform)
        #self.selectBox.setAngle(self.userRotate)
        #self.selectBox.setPos([x2, y2])
        self.selectBox.blockSignals(False)
        

    def selectBoxToItem(self):
        """Move/scale the selection box so it fits the item's bounding rect. (assumes item is not rotated)"""
        rect = self.item.sceneBoundingRect()
        self.itemRect = self.item.boundingRect()
        self.selectBox.blockSignals(True)
        self.selectBox.setPos([rect.x(), rect.y()])
        self.selectBox.setSize(rect.size())
        self.selectBox.setAngle(0)
        self.selectBox.blockSignals(False)

    def zValue(self):
        return self.opts['z']
        
    def setZValue(self, z):
        self.opts['z'] = z
        if z is not None:
            self.item.setZValue(z)
        
    def selectionChanged(self, canvas, items):
        self.selected = len(items) == 1 and (items[0] is self) 
        self.showSelectBox()
            
                
    def selectBoxChanged(self):
        self.selectBoxMoved()
        #self.updateTransform(self.selectBox)
        #self.emit(QtCore.SIGNAL('transformChanged'), self)
        self.sigTransformChanged.emit(self)
        
    def selectBoxChangeFinished(self):
        #self.emit(QtCore.SIGNAL('transformChangeFinished'), self)
        self.sigTransformChangeFinished.emit(self)

    def alphaPressed(self):
        """Hide selection box while slider is moving"""
        self.hideSelectBox()
        
    def alphaReleased(self):
        self.showSelectBox()
        
    def showSelectBox(self):
        """Display the selection box around this item if it is selected and movable"""
        if self.selected and self.isMovable() and self.isVisible() and len(self.canvas.itemList.selectedItems())==1:
            self.selectBox.show()
        else:
            self.selectBox.hide()
        
    def hideSelectBox(self):
        self.selectBox.hide()
        
    def show(self):
        if self.opts['visible']:
            return
        self.opts['visible'] = True
        self.item.show()
        self.showSelectBox()
        self.sigVisibilityChanged.emit(self)
        
    def hide(self):
        if not self.opts['visible']:
            return
        self.opts['visible'] = False
        self.item.hide()
        self.hideSelectBox()
        self.sigVisibilityChanged.emit(self)

    def setVisible(self, vis):
        if vis:
            self.show()
        else:
            self.hide()

    def isVisible(self):
        return self.opts['visible']




class MarkerCanvasItem(CanvasItem):
    def __init__(self, canvas, **opts):
        item = QtGui.QGraphicsEllipseItem(-0.5, -0.5, 1., 1.)
        item.setPen(pg.mkPen((255,255,255)))
        item.setBrush(pg.mkBrush((0,100,255)))
        CanvasItem.__init__(self, canvas, item, **opts)
        
class ScanCanvasItem(CanvasItem):
    def __init__(self, canvas, item, **opts):
        
        #print "Creating ScanCanvasItem...."
        CanvasItem.__init__(self, canvas, item, **opts)
        
        self.addScanImageBtn = QtGui.QPushButton()
        self.addScanImageBtn.setText('Add Scan Image')
        self.layout.addWidget(self.addScanImageBtn,4,0,1,2)
        
        self.addScanImageBtn.connect(self.addScanImageBtn, QtCore.SIGNAL('clicked()'), self.loadScanImage)
        
    def loadScanImage(self):
        #print 'loadScanImage called.'
        #dh = self.ui.fileLoader.ui.dirTree.selectedFile()
        #scan = self.canvas.selectedItem()
        dh = self.opts['handle']
        dirs = [dh[d] for d in dh.subDirs()]
        if 'Camera' not in dirs[0].subDirs():
            print "No image data for this scan."
            return
        
        images = []
        nulls = []
        for d in dirs:
            if 'Camera' not in d.subDirs():
                continue
            frames = d['Camera']['frames.ma'].read()
            image = frames[1]-frames[0]
            image[frames[0] > frames[1]] = 0.  ## unsigned type; avoid negative values
            mx = image.max()
            if mx < 50:
                nulls.append(d.shortName())
                continue
            image *= (1000. / mx)
            images.append(image)
            
        print "Null frames for %s:" %dh.shortName(), nulls
        scanImages = np.zeros(images[0].shape)
        for im in images:
            mask = im > scanImages
            scanImages[mask] = im[mask]
        
        info = dirs[0]['Camera']['frames.ma'].read()._info[-1]
    
        pos =  info['imagePosition']
        scale = info['pixelSize']
        item = self.canvas.addImage(scanImages, pos=pos, scale=scale, z=self.opts['z']-1, name='scanImage')
        self.scanImage = item
        
        self.scanImage.restoreTransform(self.saveTransform())
        
        #self.canvas.items[item] = scanImages
        


class ImageCanvasItem(CanvasItem):
    def __init__(self, canvas, image, **opts):
        item = None
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
                    opts['scale'] = info.get('pixelSize', None)
                    opts['pos'] = info.get('imagePosition', None)
            except:
                pass
        
        showTime = False
        if item is None:
            if self.data.ndim == 3:
                if self.data.shape[2] <= 4: ## assume last axis is color
                    #self.data = self.data.mean(axis=2)
                    item = graphicsItems.ImageItem(self.data)
                else:
                    item = graphicsItems.ImageItem(self.data[0])
                    showTime = True
            else:
                item = graphicsItems.ImageItem(self.data)
        CanvasItem.__init__(self, canvas, item, **opts)
        
        self.histogram = PlotWidget()
        self.blockHistogram = False
        self.histogram.setMaximumHeight(100)
        self.levelRgn = graphicsItems.LinearRegionItem(self.histogram)
        self.histogram.addItem(self.levelRgn)
        
        self.updateHistogram(autoRange=True)
        
        self.layout.addWidget(self.histogram, self.layout.rowCount(), 0, 1, 2)
        
        if showTime:
            self.timeSlider = QtGui.QSlider(QtCore.Qt.Horizontal)
            self.timeSlider.setMinimum(0)
            self.timeSlider.setMaximum(self.data.shape[0]-1)
            self.layout.addWidget(self.timeSlider, self.layout.rowCount(), 0, 1, 2)
            self.timeSlider.valueChanged.connect(self.timeChanged)
            self.timeSlider.sliderPressed.connect(self.timeSliderPressed)
            self.timeSlider.sliderReleased.connect(self.timeSliderReleased)
            self.maxBtn = QtGui.QPushButton('Max')
            self.maxBtn.clicked.connect(self.maxClicked)
            self.layout.addWidget(self.maxBtn, self.layout.rowCount(), 0, 1, 2)
            
        
        #self.item.connect(self.item, QtCore.SIGNAL('imageChanged'), self.updateHistogram)
        self.item.sigImageChanged.connect(self.updateHistogram)
        #self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChanged'), self.levelsChanged)
        self.levelRgn.sigRegionChanged.connect(self.levelsChanged)
        #self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChangeFinished'), self.levelsChangeFinished)
        self.levelRgn.sigRegionChangeFinished.connect(self.levelsChangeFinished)
        
        
        #self.timeSlider
        
    def timeChanged(self, t):
        self.item.updateImage(self.data[t])
        
    def timeSliderPressed(self):
        self.blockHistogram = True
        
        
    def maxClicked(self):
        ## unsharp mask to enhance fine details
        fd = self.data.astype(float)
        blur = ndimage.gaussian_filter(fd, (0, 1, 1))
        blur2 = ndimage.gaussian_filter(fd, (0, 2, 2))
        dif = blur - blur2
        #dif[dif < 0.] = 0
        self.item.updateImage(dif.max(axis=0))
        self.updateHistogram(autoRange=True)
            
        
    def timeSliderReleased(self):
        self.blockHistogram = False
        self.updateHistogram()
        
        
    def updateHistogram(self, autoRange=False):
        if self.blockHistogram:
            return
        x, y = self.item.getHistogram()
        self.histogram.clearPlots()
        self.histogram.plot(x, y)
        if autoRange:
            self.item.updateImage(autoRange=True)
            w, b = self.item.getLevels()
            self.levelRgn.blockSignals(True)
            self.levelRgn.setRegion([w, b])
            self.levelRgn.blockSignals(False)
            
        
    def levelsChanged(self):
        rgn = self.levelRgn.getRegion()
        self.item.setLevels(rgn[1], rgn[0])
        self.hideSelectBox()

    def levelsChangeFinished(self):
        self.showSelectBox()






if __name__ == '__main__':
    app = QtGui.QApplication([])
    w1 = QtGui.QMainWindow()
    c1 = Canvas(name="Canvas1")
    w1.setCentralWidget(c1)
    w1.show()
    w1.resize(600, 600)
    
    w2 = QtGui.QMainWindow()
    c2 = Canvas(name="Canvas2")
    w2.setCentralWidget(c2)
    w2.show()
    w2.resize(600, 600)
    

    import numpy as np
    
    img1 = np.random.normal(size=(200, 200))
    img2 = np.random.normal(size=(200, 200))
    def fn(x, y):
        return (x**2 + y**2)**0.5
    img1 += np.fromfunction(fn, (200, 200))
    img2 += np.fromfunction(lambda x,y: fn(x-100, y-100), (200, 200))
    
    img3 = np.random.normal(size=(200, 200, 200))
    
    i1 = c1.addImage(img1, scale=[0.01, 0.01], name="Image 1", z=10)
    i2 = c1.addImage(img2, scale=[0.01, 0.01], pos=[-1, -1], name="Image 2", z=100)
    i3 = c1.addImage(img3, scale=[0.01, 0.01], pos=[1, -1], name="Image 3", z=-100)
    i1.setMovable(True)
    i2.setMovable(True)
    