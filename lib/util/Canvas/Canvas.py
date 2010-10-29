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


class Canvas(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.view = self.ui.view
        self.itemList = self.ui.itemList
        #self.ui.levelsSlider.setOrientation('bottom')
        
        self.items = {}
        self.scans = {}
        #self.itemList = QtGui.QTreeWidget()
        #self.layout = QtGui.QHBoxLayout()
        #self.setLayout(self.layout)
        #self.view = GraphicsView()
        import sys
        if 'linux' in sys.platform.lower():
            self.view.useOpenGL(False)
        #self.layout.addWidget(self.view)
        #self.layout.addWidget(self.itemList)
        
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
        self.grid = graphicsItems.GridItem(self.view)
        #self.view.addItem(self.grid)
        #self.grid.hide()
        self.addItem(self.grid, name='Grid')
        
        
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
            gi.item.show()
        else:
            gi.item.hide()

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
                pts.append({'pos': pos, 'size': size})
        
        item = graphicsItems.ScatterPlotItem(pts, pxMode=False)
        citem = CanvasItem(self, item, **opts)
        self._addCanvasItem(citem)
        return citem
        
    def addFile(self, fh, **opts):
        if fh.isFile():
            return self.addImage(fh, **opts)
        else:
            return self.addScan(fh, **opts)


    def _addCanvasItem(self, citem):
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
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items
        
    def getItem(self, name):
        return self.items[name]
        
    def scene(self):
        return self.view.scene()
        

class SelectBox(widgets.ROI):
    def __init__(self):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        widgets.ROI.__init__(self, [0,0], [1,1])
        center = [0.5, 0.5]
            
        self.addScaleHandle([1, 1], center)
        self.addScaleHandle([0, 0], center)
        self.addRotateHandle([0, 1], center)
        self.addRotateHandle([1, 0], center)


class CanvasItem(QtCore.QObject):
    """CanvasItem takes care of managing an item's state--alpha, visibility, z-value, transformations, etc. and
    provides a control widget"""
    def __init__(self, canvas, item, **opts):
        defOpts = {'name': None, 'pos': [0,0], 'scale': [1,1], 'z': None, 'movable': False}
        defOpts.update(opts)
        self.opts = defOpts
        self.selected = False
        
        QtCore.QObject.__init__(self)
        self.canvas = canvas
        self.item = item
        
        self.transform = QtGui.QTransform()
        
        self.updateItem()



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
        self.connect(self.alphaSlider, QtCore.SIGNAL('valueChanged(int)'), self.alphaChanged)
        self.connect(self.alphaSlider, QtCore.SIGNAL('sliderPressed()'), self.alphaPressed)
        self.connect(self.alphaSlider, QtCore.SIGNAL('sliderReleased()'), self.alphaReleased)
        self.connect(self.canvas, QtCore.SIGNAL('itemSelected'), self.selectionChanged)

        self.selectBox = SelectBox()
        self.canvas.scene().addItem(self.selectBox)
        self.selectBox.hide()
        self.selectBox.setZValue(1e6)
        self.selectBox.connect(self.selectBox, QtCore.SIGNAL('regionChanged'), self.selectBoxChanged)
        self.selectBox.setPos(self.item.pos())
        self.selectBox.setSize(self.item.sceneBoundingRect().size())


    def ctrlWidget(self):
        return self.ctrl
        
    def alphaChanged(self, val):
        alpha = val / 1023.
        self.item.setOpacity(alpha)
        
    def isMovable(self):
        return self.opts['movable']
        
    def setMovable(self, m):
        self.opts['movable'] = m
            
    def updateTransform(self, box):
        self.transform = QtGui.QTransform()
        st = self.selectBox.getState()
        self.transform.translate(st['pos'][0]-self.opts['pos'][0], st['pos'][1]-self.opts['pos'][1])
        self.transform.rotate(-st['angle']*180./3.1415926)
        self.updateItem()

    def updateItem(self):
        scale = self.opts['scale']
        pos = self.opts['pos']
        self.item.resetTransform()
        self.item.setPos(QtCore.QPointF(pos[0], pos[1]))
        self.item.scale(scale[0], scale[1])
        
        ## add in user transform
        self.item.setTransform(self.item.transform() * self.transform)
        

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
        self.updateTransform(self.selectBox)

    def alphaPressed(self):
        """Hide selection box while slider is moving"""
        self.hideSelectBox()
        
    def alphaReleased(self):
        self.showSelectBox()
        
    def showSelectBox(self):
        """Display the selection box around this item if it is selected and movable"""
        if self.selected and self.isMovable():
            self.selectBox.show()
        else:
            self.selectBox.hide()
        
    def hideSelectBox(self):
        self.selectBox.hide()
        

class ImageCanvasItem(CanvasItem):
    def __init__(self, canvas, image, **opts):
        if isinstance(image, QtGui.QGraphicsItem):
            item = image
        elif isinstance(image, np.ndarray):
            self.data = image
            if self.data.ndim == 3:
                item = graphicsItems.ImageItem(image[0])
            else:
                item = graphicsItems.ImageItem(image)
        elif isinstance(image, DataManager.FileHandle):
            self.handle = image
            self.data = self.handle.read()
            item = graphicsItems.ImageItem(image)
        
        CanvasItem.__init__(self, canvas, item, **opts)
        
        self.histogram = PlotWidget()
        self.histogram.setMaximumHeight(100)
        self.levelRgn = graphicsItems.LinearRegionItem(self.histogram)
        self.histogram.addItem(self.levelRgn)
        
        self.updateHistogram(autoRange=True)
        
        self.layout.addWidget(self.histogram, 1, 0, 1, 2)
        #self.connect(self.ui.minLevelSpin, QtCore.SIGNAL('valueChanged'), self.updateLevels)
        #self.connect(self.ui.maxLevelSpin, QtCore.SIGNAL('valueChanged'), self.updateLevels)
        #self.connect(self.ui.levelsSlider, QtCore.SIGNAL('gradientChanged'), self.updateLevels)
        self.item.connect(self.item, QtCore.SIGNAL('imageChanged'), self.updateHistogram)
        self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChanged'), self.levelsChanged)
        self.levelRgn.connect(self.levelRgn, QtCore.SIGNAL('regionChangeFinished'), self.levelsChangeFinished)
        
    def updateHistogram(self, autoRange=False):
        x, y = self.item.getHistogram()
        self.histogram.plot(y, x)
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
    