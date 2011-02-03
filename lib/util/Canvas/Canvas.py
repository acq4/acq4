# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import sys, os
    md = os.path.dirname(os.path.abspath(__file__))
    sys.path = [os.path.dirname(md)] + sys.path
    #print md
    
from CanvasTemplate import *
from pyqtgraph.GraphicsView import GraphicsView
import pyqtgraph.graphicsItems as graphicsItems
from pyqtgraph.PlotWidget import PlotWidget
from pyqtgraph import widgets
from PyQt4 import QtGui, QtCore
import DataManager
import numpy as np
import debug

class Canvas(QtGui.QWidget):
    def __init__(self, parent=None, allowTransforms=True):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.view = self.ui.view
        self.itemList = self.ui.itemList
        #self.ui.levelsSlider.setOrientation('bottom')
        self.allowTransforms = allowTransforms
        
        self.items = {}
        self.scans = {}
        #self.itemList = QtGui.QTreeWidget()
        #self.layout = QtGui.QHBoxLayout()
        #self.setLayout(self.layout)
        #self.view = GraphicsView()
        
        #import sys
        #if 'linux' in sys.platform.lower():
            #self.view.useOpenGL(False)
            
        #self.layout.addWidget(self.view)
        #self.layout.addWidget(self.itemList)
        
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
        self.grid = graphicsItems.GridItem(self.view)
        #self.view.addItem(self.grid)
        #self.grid.hide()
        self.addItem(self.grid, name='Grid', movable=False)
        
        
        self.hideBtn = QtGui.QPushButton('>', self)
        self.hideBtn.setFixedWidth(20)
        self.hideBtn.setFixedHeight(20)
        self.ctrlSize = 200
        self.connect(self.hideBtn, QtCore.SIGNAL('clicked()'), self.hideBtnClicked)
        self.connect(self.ui.splitter, QtCore.SIGNAL('splitterMoved(int, int)'), self.splitterMoved)
        #self.connect(self.ui.gridCheck, QtCore.SIGNAL('stateChanged(int)'), self.gridCheckChanged)
        
        self.connect(self.ui.itemList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.treeItemChanged)
        self.connect(self.ui.itemList, QtCore.SIGNAL('itemMoved'), self.treeItemMoved)
        self.connect(self.ui.itemList, QtCore.SIGNAL('itemSelectionChanged()'), self.treeItemSelected)
        self.connect(self.ui.autoRangeBtn, QtCore.SIGNAL('clicked()'), self.autoRangeClicked)
        self.resizeEvent()

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

    #def gridCheckChanged(self, v):
        #if self.ui.gridCheck.isChecked():
            #self.grid.show()
        #else:
            #self.grid.hide()

    def updateLevels(self):
        gi = self.selectedItem()
        if gi is None:
            return
            
        mn = self.ui.minLevelSpin.value()
        mx = self.ui.maxLevelSpin.value()
        levels = self.ui.levelsSlider.getLevels()
        bl = mn + levels[0] * (mx-mn)
        wl = mn + levels[1] * (mx-mn)
        gi.setLevels(wl, bl)



    def treeItemChanged(self, item, col):
        gi = self.items.get(item.name, None)
        if gi is None:
            return
        if item.checkState(0) == QtCore.Qt.Checked:
            gi.show()
        else:
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
        sel = self.itemList.selectedItems()[0]
        if sel is None:
            #self.selectWidget.hide()
            return
        for i in self.items.itervalues():
            i.ctrlWidget().hide()
        item = self.items[sel.name]
        item.ctrlWidget().show()
        
        #if item.isMovable():
            #self.selectBox.setPos(item.item.pos())
            #self.selectBox.setSize(item.item.sceneBoundingRect().size())
            #self.selectBox.show()
        #else:
            #self.selectBox.hide()
        
        self.emit(QtCore.SIGNAL('itemSelected'), self, item)

    def selectedItem(self):
        sel = self.itemList.selectedItems()
        if sel is None or len(sel) < 1:
            return
        return self.items.get(sel[0].name, None)


    def addItem(self, item, **opts):
        """Add a new item to the scene at pos.
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
    
    def addScan(self, dirHandle, **opts):
        if len(dirHandle.info()['protocol']['params']) > 0:
            dirs = [dirHandle[d] for d in dirHandle.subDirs()]
        else:
            dirs = [dirHandle]
            
        if 'name' not in opts:
            opts['name'] = dirHandle.shortName()
            
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
        citem = CanvasItem(self, item, handle=dirHandle, **opts)
        self._addCanvasItem(citem)
        return citem
        
    def addFile(self, fh, **opts):
        if fh.isFile():
            return self.addImage(fh, **opts)
        else:
            return self.addScan(fh, **opts)


    def _addCanvasItem(self, citem):
        """Obligatory function call for any idems added to the canvas."""
        
        if not self.allowTransforms:
            citem.setMovable(False)
        
        item = citem.item
        name = citem.name
        
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
        currentNode = self.itemList.invisibleRootItem()
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
                
        self.connect(citem, QtCore.SIGNAL('transformChanged'), self.itemTransformChanged)
        self.connect(citem, QtCore.SIGNAL('transformChangeFinished'), self.itemTransformChangeFinished)
        #print name, insertLocation, z
        
        node = QtGui.QTreeWidgetItem([name])
        node.setFlags((node.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsDragEnabled) & ~QtCore.Qt.ItemIsDropEnabled)
        node.setCheckState(0, QtCore.Qt.Checked)
        node.name = name
        root.insertChild(insertLocation, node)
        
        #citem = CanvasItem(self, name, item)
        citem.name = name
        node.item = citem
        self.items[name] = citem

        ctrl = citem.ctrlWidget()
        ctrl.hide()
        self.ui.ctrlLayout.addWidget(ctrl)

        #self.items[tuple(name)] = item
        return name
        

    def removeItem(self, item):
        self.view.scene().removeItem(item)
        
        ## disconnect signals, remove from list, etc..
        
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items
        
    def getItem(self, name):
        return self.items[name]
        
    def scene(self):
        return self.view.scene()
        
    def itemTransformChanged(self, item):
        self.emit(QtCore.SIGNAL('itemTransformChanged'), self, item)
    
    def itemTransformChangeFinished(self, item):
        self.emit(QtCore.SIGNAL('itemTransformChangeFinished'), self, item)
        


class SelectBox(widgets.ROI):
    def __init__(self):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        widgets.ROI.__init__(self, [0,0], [1,1])
        center = [0.5, 0.5]
            
        #self.addScaleHandle([1, 1], center)
        #self.addScaleHandle([0, 0], center)
        self.addRotateHandle([0, 1], center)
        self.addRotateHandle([1, 0], center)


class CanvasItem(QtCore.QObject):
    """CanvasItem takes care of managing an item's state--alpha, visibility, z-value, transformations, etc. and
    provides a control widget"""
    def __init__(self, canvas, item, **opts):
        defOpts = {'name': None, 'pos': [0,0], 'scale': [1,1], 'z': None, 'movable': True, 'handle': None, 'visible': True}
        defOpts.update(opts)
        self.opts = defOpts
        self.selected = False
        
        QtCore.QObject.__init__(self)
        self.canvas = canvas
        self.item = item
        

        z = self.opts['z']
        if z is not None:
            item.setZValue(z)
        
        #if scale is None:
            #scale = [1, 1]
        #if pos is None:
            #pos = [0,0]
        

        self.name = self.opts['name']
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
        self.layout.addWidget(self.resetTransformBtn, 1, 0, 1, 2)
        self.connect(self.alphaSlider, QtCore.SIGNAL('valueChanged(int)'), self.alphaChanged)
        self.connect(self.alphaSlider, QtCore.SIGNAL('sliderPressed()'), self.alphaPressed)
        self.connect(self.alphaSlider, QtCore.SIGNAL('sliderReleased()'), self.alphaReleased)
        self.connect(self.canvas, QtCore.SIGNAL('itemSelected'), self.selectionChanged)
        self.connect(self.resetTransformBtn, QtCore.SIGNAL('clicked()'), self.resetTransformClicked)
        
        self.selectBox = SelectBox()
        self.canvas.scene().addItem(self.selectBox)
        self.selectBox.hide()
        self.selectBox.setZValue(1e6)
        self.selectBox.connect(self.selectBox, QtCore.SIGNAL('regionChanged'), self.selectBoxChanged)  ## calls selectBoxMoved
        self.selectBox.connect(self.selectBox, QtCore.SIGNAL('regionChangeFinished'), self.selectBoxChangeFinished)
        #self.selectBoxToItem()

        #self.item.translate(*self.opts['pos'])
        #self.item.scale(*self.opts['scale'])
        
        
        self.basePos = self.opts['pos']
        self.baseScale = self.opts['scale']
        #self.baseTransform = self.transform()
        self.resetTransform()
        self.selectBoxBase = self.selectBox.getState().copy()
        
        if self.opts['handle'] is not None:
            trans = self.opts['handle'].info().get('userTransform', None)
            if trans is not None:
                self.restoreTransform(trans)

    def hasUserTransform(self):
        #print self.userRotate, self.userTranslate
        if self.userRotate == 0 and self.userTranslate == [0,0]:
            return False
        else:
            return True

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
        #self.transform = QtGui.QTransform()
        st = self.selectBox.getState()
        
        bpos = st['pos']
        
        ## How far the box has moved from its starting position
        trans = [bpos[0] - self.selectBoxBase['pos'][0], bpos[1] - self.selectBoxBase['pos'][1]]
        
        ## rotation
        ang = -st['angle'] * 180. / 3.14159265358
        rot = QtGui.QTransform()
        rot.rotate(ang)
        
        ## base position, rotated
        p1x, p1y = rot.map(*self.basePos)
        
        ## translation left over after rotation
        t2x = trans[0]-(p1x-self.basePos[0])
        t2y = trans[1]-(p1y-self.basePos[1])
        
        ## Need to reverse translate and rotate operations to make them relative to origin
        #t = QtCore.QPointF(*trans)
        #ang = -st['angle'] * 180. / 3.14159265358
        #rot = QtGui.QTransform()
        #rot.rotate(-ang)
        #t1 = rot.map(t)
        
        self.userTranslate = [t2x, t2y]
        self.userRotate = st['angle']
        
        self.updateTransform()
        
    def transform(self):
        return self.item.transform()

    def updateTransform(self):
        """Regenerate the item position from the base and user transform"""
        ## user transform portion
        trans = QtGui.QTransform()
        trans.translate(*self.userTranslate)
        trans.rotate(-self.userRotate*180./3.14159265358)

        ## add base transform
        trans.translate(*self.basePos)
        trans.scale(*self.baseScale)
        self.item.setTransform(trans)
        

    def resetTransform(self):
        #self.transform = QtGui.QTransform()
        #scale = self.opts['scale']
        #pos = self.opts['pos']
        #self.transform.translate(pos[0], pos[1])
        #self.transform.scale(scale[0], scale[1])
        
        ### update the graphics item
        #self.item.setTransform(self.transform)
        #self.hasUserTransform = False
        #print "reset transform", self
        self.userRotate = 0
        self.userTranslate = [0,0]
        self.updateTransform()
        
        self.selectBox.blockSignals(True)
        self.selectBoxToItem()
        self.selectBox.blockSignals(False)
        self.emit(QtCore.SIGNAL('transformChanged'), self)
        self.emit(QtCore.SIGNAL('transformChangeFinished'), self)
        
    def resetTransformClicked(self):
        self.resetTransform()
        self.emit(QtCore.SIGNAL('resetUserTransform'), self)
        
        
    #def applyTransform(self, t):
        #return
        #self.transform  = t * self.transform
        ### update the graphics item
        #self.hasUserTransform = True
        #self.item.setTransform(self.transform)
        #self.selectBox.blockSignals(True)
        #self.selectBox.
        ##self.selectBoxToItem()
        #self.selectBox.blockSignals(False)
        #self.emit(QtCore.SIGNAL('transformChangeFinished'), self)
        
    def restoreTransform(self, tr):
        try:
            self.userTranslate = tr['trans']
            self.userRotate = tr['rot']
            
            self.selectBoxFromUser() ## move select box to match
            self.updateTransform()
            self.emit(QtCore.SIGNAL('transformChanged'), self)
            self.emit(QtCore.SIGNAL('transformChangeFinished'), self)
        except:
            self.userTranslate = [0,0]
            self.userRotate = 0
            debug.printExc("Failed to load transform:")
        #print "set transform", self, self.userTranslate
        
    def saveTransform(self):
        #print "save transform", self, self.userTranslate
        return {'trans': self.userTranslate[:], 'rot': self.userRotate}
        
    def selectBoxFromUser(self):
        """Move the selection box to match the current userTransform"""
        ## user transform
        trans = QtGui.QTransform()
        trans.translate(*self.userTranslate)
        trans.rotate(-self.userRotate*180./3.14159265358)
        
        x2, y2 = trans.map(*self.selectBoxBase['pos'])
        
        self.selectBox.blockSignals(True)
        self.selectBox.setAngle(self.userRotate)
        self.selectBox.setPos([x2, y2])
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

    #def saveTransform(self):
        #state = {'translate': self.userTranslate, 'rotate': self.userRotate}
        ##state = self.selectBox.getState()
        ##state['pos'] = list(state['pos'])
        ##state['size'] = list(state['size'])
        ##print "save:", state
        #return state

    #def restoreTransform(self, trans):
        #self.resetTransform()
        #self.userTranslate = trans['translate']
        #self.userRotate = trans['rotate']
        #self.updateTransform()
        
        #self.selectBox.blockSignals(True)
        ##pos = self.selectBoxBase['pos']
        #state = self.selectBox.getState()
        ##print "restore:", state, " -> ", trans
        #pos = state['pos']
        #t = trans['translate']
        #state['pos'] = [pos[0]+t[0], pos[1]+t[1]]
        #state['angle'] = trans['rotate']
        ##state = {'pos': [pos[0]+t[0], pos[1]+t[1]], 'angle': trans['rotate']}
        #self.selectBox.setState(state)
        #self.selectBox.blockSignals(False)

    def zValue(self):
        return self.opts['z']
        
    def setZValue(self, z):
        self.opts['z'] = z
        if z is not None:
            self.item.setZValue(z)
        
    def selectionChanged(self, canvas, item):
        self.selected = (item is self)
        self.showSelectBox()
        
    def selectBoxChanged(self):
        self.selectBoxMoved()
        #self.updateTransform(self.selectBox)
        self.emit(QtCore.SIGNAL('transformChanged'), self)
        
    def selectBoxChangeFinished(self):
        self.emit(QtCore.SIGNAL('transformChangeFinished'), self)

    def alphaPressed(self):
        """Hide selection box while slider is moving"""
        self.hideSelectBox()
        
    def alphaReleased(self):
        self.showSelectBox()
        
    def showSelectBox(self):
        """Display the selection box around this item if it is selected and movable"""
        if self.selected and self.isMovable() and self.isVisible():
            self.selectBox.show()
        else:
            self.selectBox.hide()
        
    def hideSelectBox(self):
        self.selectBox.hide()
        
    def show(self):
        self.opts['visible'] = True
        self.item.show()
        self.showSelectBox()
        
    def hide(self):
        self.opts['visible'] = False
        self.item.hide()
        self.hideSelectBox()
        
    def isVisible(self):
        return self.opts['visible']

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
        
        if item is None:
            if self.data.ndim == 3:
                if self.data.shape[2] <= 4:
                    self.data = self.data.mean(axis=2)
                    item = graphicsItems.ImageItem(self.data)
                else:
                    item = graphicsItems.ImageItem(self.data[0])
            else:
                item = graphicsItems.ImageItem(self.data)
        CanvasItem.__init__(self, canvas, item, **opts)
        
        self.histogram = PlotWidget()
        self.histogram.setMaximumHeight(100)
        self.levelRgn = graphicsItems.LinearRegionItem(self.histogram)
        self.histogram.addItem(self.levelRgn)
        
        self.updateHistogram(autoRange=True)
        
        self.layout.addWidget(self.histogram, self.layout.rowCount(), 0, 1, 2)
        #self.connect(self.ui.minLevelSpin, QtCore.SIGNAL('valueChanged'), self.updateLevels)
        #self.connect(self.ui.maxLevelSpin, QtCore.SIGNAL('valueChanged'), self.updateLevels)
        #self.connect(self.ui.levelsSlider, QtCore.SIGNAL('gradientChanged'), self.updateLevels)
        self.item.connect(self.item, QtCore.SIGNAL('imageChanged'), self.updateHistogram)
        self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChanged'), self.levelsChanged)
        self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChangeFinished'), self.levelsChangeFinished)
        
        
        #self.timeSlider
        
        
    def updateHistogram(self, autoRange=False):
        x, y = self.item.getHistogram()
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
    w = QtGui.QMainWindow()
    c = Canvas()
    w.setCentralWidget(c)
    w.show()
    w.resize(600, 600)
    
    
    import numpy as np
    
    img1 = np.random.normal(size=(200, 200))
    img2 = np.random.normal(size=(200, 200))
    def fn(x, y):
        return (x**2 + y**2)**0.5
    img1 += np.fromfunction(fn, (200, 200))
    img2 += np.fromfunction(lambda x,y: fn(x-100, y-100), (200, 200))
    
    img3 = np.random.normal(size=(200, 200, 200))
    
    i1 = c.addImage(img1, scale=[0.01, 0.01], name="Image 1", z=10)
    i2 = c.addImage(img2, scale=[0.01, 0.01], pos=[-1, -1], name="Image 2", z=100)
    i3 = c.addImage(img3, scale=[0.01, 0.01], pos=[1, -1], name="Image 3", z=-100)
    i1.setMovable(True)
    i2.setMovable(True)
    