# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import sys, os
    md = os.path.dirname(os.path.abspath(__file__))
    sys.path = [os.path.dirname(md)] + sys.path
    #print md
    
from CanvasTemplate import *
#from pyqtgraph.GraphicsView import GraphicsView
#import pyqtgraph.graphicsItems as graphicsItems
#from pyqtgraph.PlotWidget import PlotWidget
from pyqtgraph import widgets
from PyQt4 import QtGui, QtCore
#import DataManager
import numpy as np
import debug
import pyqtgraph as pg
import weakref
from CanvasManager import CanvasManager
import items

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
        self.ui.mirrorSelectionBtn.hide()
        self.ui.resetTransformsBtn.hide()
        
        self.redirect = None  ## which canvas to redirect items to
        self.items = []
        
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
        grid = pg.GridItem(self.view)
        self.grid = items.CanvasItem(grid, name='Grid', movable=False)
        self.addItem(self.grid)
        
        self.hideBtn = QtGui.QPushButton('>', self)
        self.hideBtn.setFixedWidth(20)
        self.hideBtn.setFixedHeight(20)
        self.ctrlSize = 200
        self.hideBtn.clicked.connect(self.hideBtnClicked)
        self.ui.splitter.splitterMoved.connect(self.splitterMoved)
        
        self.ui.itemList.itemChanged.connect(self.treeItemChanged)
        self.ui.itemList.sigItemMoved.connect(self.treeItemMoved)
        self.ui.itemList.itemSelectionChanged.connect(self.treeItemSelected)
        self.ui.autoRangeBtn.clicked.connect(self.autoRange)
        self.ui.storeSvgBtn.clicked.connect(self.storeSvg)
        self.ui.storePngBtn.clicked.connect(self.storePng)
        self.ui.redirectCheck.toggled.connect(self.updateRedirect)
        self.ui.redirectCombo.currentIndexChanged.connect(self.updateRedirect)
        self.multiSelectBox.sigRegionChanged.connect(self.multiSelectBoxChanged)
        self.multiSelectBox.sigRegionChangeFinished.connect(self.multiSelectBoxChangeFinished)
        self.ui.mirrorSelectionBtn.clicked.connect(self.mirrorSelectionClicked)
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

    def autoRange(self):
        items = []
        #for i in range(self.itemList.topLevelItemCount()):
            #name = self.itemList.topLevelItem(i).name
            #citem = self.items[name]
        for citem in self.items:
            if citem.isVisible() and citem is not self.grid:
                items.append(citem.graphicsItem())
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
        for i in self.items:
            if i is self.grid:
                continue
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
            canvas.addItem(i)
            

    def reclaimItems(self):
        items = self.items
        #self.items = {'Grid': items['Grid']}
        #del items['Grid']
        self.items = [self.grid]
        items.remove(self.grid)
        
        for i in items:
            i.canvas.removeItem(i)
            self.addItem(i)

    def treeItemChanged(self, item, col):
        #gi = self.items.get(item.name, None)
        #if gi is None:
            #return
        try:
            citem = item.canvasItem
        except AttributeError:
            return
        if item.checkState(0) == QtCore.Qt.Checked:
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, QtCore.Qt.Checked)
            citem.show()
        else:
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, QtCore.Qt.Unchecked)
            citem.hide()

    def treeItemSelected(self):
        sel = self.selectedItems()
        #sel = []
        #for listItem in self.itemList.selectedItems():
            #if hasattr(listItem, 'canvasItem') and listItem.canvasItem is not None:
                #sel.append(listItem.canvasItem)
        #sel = [self.items[item.name] for item in sel]
        
        if len(sel) == 0:
            #self.selectWidget.hide()
            return
            
        multi = len(sel) > 1
        for i in self.items:
            #i.ctrlWidget().hide()
            ## updated the selected state of every item
            i.selectionChanged(i in sel, multi)
            
        if len(sel)==1:
            #item = sel[0]
            #item.ctrlWidget().show()
            self.multiSelectBox.hide()
            self.ui.mirrorSelectionBtn.hide()
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
        
    def selectedItems(self):
        """
        Return list of all selected canvasItems
        """
        return [item.canvasItem for item in self.itemList.selectedItems() if item.canvasItem is not None]
        
    #def selectedItem(self):
        #sel = self.itemList.selectedItems()
        #if sel is None or len(sel) < 1:
            #return
        #return self.items.get(sel[0].name, None)

    def selectItem(self, item):
        li = item.listItem
        #li = self.getListItem(item.name())
        #print "select", li
        self.itemList.setCurrentItem(li)

        
        
    def showMultiSelectBox(self):
        ## Get list of selected canvas items
        items = self.selectedItems()
        
        rect = items[0].graphicsItem().sceneBoundingRect()
        for i in items:
            if not i.isMovable():  ## all items in selection must be movable
                return
            br = i.graphicsItem().sceneBoundingRect()
            rect = rect|br
            
        self.multiSelectBox.blockSignals(True)
        self.multiSelectBox.setPos([rect.x(), rect.y()])
        self.multiSelectBox.setSize(rect.size())
        self.multiSelectBox.setAngle(0)
        self.multiSelectBox.blockSignals(False)
        
        self.multiSelectBox.show()
        
        self.ui.mirrorSelectionBtn.show()
        self.ui.resetTransformsBtn.show()
        #self.multiSelectBoxBase = self.multiSelectBox.getState().copy()

    def mirrorSelectionClicked(self):
        for ci in self.selectedItems():
            ci.mirrorY()
        self.showMultiSelectBox()
            
    def resetTransformsClicked(self):
        for i in self.selectedItems():
            i.resetTransformClicked()
        self.showMultiSelectBox()

    def multiSelectBoxChanged(self):
        self.multiSelectBoxMoved()
        
    def multiSelectBoxChangeFinished(self):
        for ci in self.selectedItems():
            ci.applyTemporaryTransform()
            ci.sigTransformChangeFinished.emit(ci)
        
    def multiSelectBoxMoved(self):
        transform = self.multiSelectBox.getGlobalTransform()
        for ci in self.selectedItems():
            ci.setTemporaryTransform(transform)
            ci.sigTransformChanged.emit(ci)
        

    def addGraphicsItem(self, item, **opts):
        """Add a new GraphicsItem to the scene at pos.
        Common options are name, pos, scale, and z
        """
        citem = items.CanvasItem(item, **opts)
        self.addItem(citem)
        return citem
            
    #def addImage(self, img, **opts):
        #citem = ImageCanvasItem(self, img, **opts)
        #self._addCanvasItem(citem)
        #return citem
    
    ### Make addScan and addImage go away entirely, plox.
    #def addScan(self, dirHandle, **opts):
        #"""Returns a list of ScanCanvasItems."""
        
        #if 'sequenceParams' in dirHandle.info():
            #dirs = [dirHandle[d] for d in dirHandle.subDirs()]
        #else:
            #dirs = [dirHandle]
            
        #if 'separateParams' not in opts:
            #separateParams = False
        #else:
            #separateParams = opts['separateParams']
            #del(opts['separateParams'])
            
        
        #### check for sequence parameters (besides targets) so that we can separate them out into individual Scans
        #paramKeys = []
        #params = dirHandle.info()['protocol']['params']
        #if len(params) > 1 and separateParams==True:
            #for i in range(len(params)):
                #k = (params[i][0], params[i][1])
                #if k != ('Scanner', 'targets'):
                    #paramKeys.append(k)
            
        #if 'name' not in opts:
            #opts['name'] = dirHandle.shortName()
            

            
        #if len(paramKeys) < 1:    
            #pts = []
            #for d in dirs: #d is a directory handle
                ##d = dh[d]
                #if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    #pos = d.info()['Scanner']['position']
                    #if 'spotSize' in d.info()['Scanner']:
                        #size = d.info()['Scanner']['spotSize']
                    #else:
                        #size = self.defaultSize
                    #pts.append({'pos': pos, 'size': size, 'data': d})
            
            #item = graphicsItems.ScatterPlotItem(pts, pxMode=False)
            #citem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            #self._addCanvasItem(citem)
            #return [citem]
        #else:
            #pts = {}
            #for d in dirs:
                #k = d.info()[paramKeys[0]]
                #if len(pts) < k+1:
                    #pts[k] = []
                #if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                    #pos = d.info()['Scanner']['position']
                    #if 'spotSize' in d.info()['Scanner']:
                        #size = d.info()['Scanner']['spotSize']
                    #else:
                        #size = self.defaultSize
                    #pts[k].append({'pos': pos, 'size': size, 'data': d})
            #spots = []
            #for k in pts.keys():
                #spots.extend(pts[k])
            #item = graphicsItems.ScatterPlotItem(spots=spots, pxMode=False)
            #parentCitem = ScanCanvasItem(self, item, handle=dirHandle, **opts)
            #self._addCanvasItem(parentCitem)
            #scans = []
            #for k in pts.keys():
                #opts['name'] = paramKeys[0][0] + '_%03d' %k
                #item = graphicsItems.ScatterPlotItem(spots=pts[k], pxMode=False)
                #citem = ScanCanvasItem(self, item, handle = dirHandle, parent=parentCitem, **opts)
                #self._addCanvasItem(citem)
                ##scans[opts['name']] = citem
                #scans.append(citem)
            #return scans
                
                
        
    def addFile(self, fh, **opts):
        ## automatically determine what item type to load from file. May invoke dataModel for extra help.
        types = items.listItems()
        
        maxScore = 0
        bestType = None
        
        for t in types:
            score = t.checkFile(fh)
            if score > maxScore:
                maxScore = score
                bestType = t
        if bestType is None:
            raise Exception("Don't know how to load file: '%s'" % str(fh))
        citem = bestType(handle=fh)
        self.addItem(citem)
        return citem
        #if fh.isFile():
            #if fh.shortName()[-4:] == '.svg':
                #return self.addSvg(fh, **opts)
            #else:
                #return self.addImage(fh, **opts)
        #else:
            #return self.addScan(fh, **opts)

    #def addMarker(self, **opts):
        #citem = MarkerCanvasItem(self, **opts)
        #self._addCanvasItem(citem)
        #return citem

    #def addSvg(self, fh, **opts):
        #item = QtSvg.QGraphicsSvgItem(fh.name())
        #return self.addItem(item, handle=fh, **opts)

    def addGroup(self, name, **kargs):
        group = items.GroupCanvasItem(name=name)
        self.addItem(group, **kargs)
        return group
        

    def addItem(self, citem):
        """
        Add an item to the canvas. 
        """
        
        ## Check for redirections
        if self.redirect is not None:
            name = self.redirect.addItem(citem)
            self.items.append(citem)
            return name

        if not self.allowTransforms:
            citem.setMovable(False)

        citem.sigTransformChanged.connect(self.itemTransformChanged)
        citem.sigTransformChangeFinished.connect(self.itemTransformChangeFinished)
        citem.sigVisibilityChanged.connect(self.itemVisibilityChanged)

        
        ## Determine name to use in the item list
        name = citem.opts['name']
        if name is None:
            name = 'item'
        newname = name

        ## If name already exists, append a number to the end
        ## NAH. Let items have the same name if they really want.
        #c=0
        #while newname in self.items:
            #c += 1
            #newname = name + '_%03d' %c
        #name = newname
            
        ## find parent and add item to tree
        #currentNode = self.itemList.invisibleRootItem()
        insertLocation = 0
        #print "Inserting node:", name
        
            
        ## determine parent list item where this item should be inserted
        parent = citem.parentItem()
        if parent is None:
            parent = self.itemList.invisibleRootItem()
        else:
            parent = parent.listItem
        
        ## set Z value above all other siblings if none was specified
        siblings = [parent.child(i).canvasItem for i in xrange(parent.childCount())]
        z = citem.zValue()
        if z is None:
            zvals = [i.zValue() for i in siblings]
            if len(zvals) == 0:
                z = 0
            else:
                z = max(zvals)+10
            citem.setZValue(z)
            
        ## determine location to insert item relative to its siblings
        for i in range(parent.childCount()):
            ch = parent.child(i)
            zval = ch.canvasItem.graphicsItem().zValue()  ## should we use CanvasItem.zValue here?
            if zval < z:
                insertLocation = i
                break
            else:
                insertLocation = i+1
                
        node = QtGui.QTreeWidgetItem([name])
        flags = node.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsDragEnabled
        if not isinstance(citem, items.GroupCanvasItem):
            flags = flags & ~QtCore.Qt.ItemIsDropEnabled
        node.setFlags(flags)
        if citem.opts['visible']:
            node.setCheckState(0, QtCore.Qt.Checked)
        else:
            node.setCheckState(0, QtCore.Qt.Unchecked)
        
        node.name = name
        #if citem.opts['parent'] != None:
            ## insertLocation is incorrect in this case
        parent.insertChild(insertLocation, node)
        #else:    
            #root.insertChild(insertLocation, node)
        
        citem.name = name
        citem.listItem = node
        node.canvasItem = citem
        self.items.append(citem)

        ctrl = citem.ctrlWidget()
        ctrl.hide()
        self.ui.ctrlLayout.addWidget(ctrl)
        
        ## inform the canvasItem that its parent canvas has changed
        citem.setCanvas(self)

        ## Autoscale to fit the first item added (not including the grid).
        if len(self.items) == 2:
            self.autoRange()
            
        
        #for n in name:
            #nextnode = None
            #for x in range(currentNode.childCount()):
                #ch = currentNode.child(x)
                #if hasattr(ch, 'name'):    ## check Z-value of current item to determine insert location
                    #zval = ch.canvasItem.zValue()
                    #if zval > z:
                        ###print "  ->", x
                        #insertLocation = x+1
                #if n == ch.text(0):
                    #nextnode = ch
                    #break
            #if nextnode is None:  ## If name doesn't exist, create it
                #nextnode = QtGui.QTreeWidgetItem([n])
                #nextnode.setFlags((nextnode.flags() | QtCore.Qt.ItemIsUserCheckable) & ~QtCore.Qt.ItemIsDropEnabled)
                #nextnode.setCheckState(0, QtCore.Qt.Checked)
                ### Add node to correct position in list by Z-value
                ###print "  ==>", insertLocation
                #currentNode.insertChild(insertLocation, nextnode)
                
                #if n == name[-1]:   ## This is the leaf; add some extra properties.
                    #nextnode.name = name
                
                #if n == name[0]:   ## This is the root; make the item movable
                    #nextnode.setFlags(nextnode.flags() | QtCore.Qt.ItemIsDragEnabled)
                #else:
                    #nextnode.setFlags(nextnode.flags() & ~QtCore.Qt.ItemIsDragEnabled)
                    
            #currentNode = nextnode
        return citem

    def treeItemMoved(self, item, parent, index):
        ##Item moved in tree; update Z values
        if parent is self.itemList.invisibleRootItem():
            item.canvasItem.setParentItem(None)
        else:
            item.canvasItem.setParentItem(parent.canvasItem)
        siblings = [parent.child(i).canvasItem for i in xrange(parent.childCount())]
        
        zvals = [i.zValue() for i in siblings]
        zvals.sort(reverse=True)
        
        for i in range(len(siblings)):
            item = siblings[i]
            item.setZValue(zvals[i])
            #item = self.itemList.topLevelItem(i)
            
            ##ci = self.items[item.name]
            #ci = item.canvasItem
            #if ci is None:
                #continue
            #if ci.zValue() != zvals[i]:
                #ci.setZValue(zvals[i])
        
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
        if isinstance(item, items.CanvasItem):
            item.setCanvas(None)
            #self.view.scene().removeItem(item.item)
            self.itemList.removeTopLevelItem(item.listItem)
            del self.items[item.name]
        else:
            self.view.scene().removeItem(item)
        
        ## disconnect signals, remove from list, etc..
        

    def addToScene(self, item):
        self.view.scene().addItem(item)
        
    def removeFromScene(self, item):
        self.view.scene().removeItem(item)

    
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












if __name__ == '__main__':
    import items
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
    
    i1 = items.ImageCanvasItem(img1, scale=[0.01, 0.01], name="Image 1", z=10)
    c1.addItem(i1)
    
    gr = c1.addGroup('itemGroup')
    i2 = items.ImageCanvasItem(img2, scale=[0.01, 0.01], pos=[-1, -1], name="Image 2", z=100, parent=gr)
    i3 = items.ImageCanvasItem(img3, scale=[0.01, 0.01], pos=[1, -1], name="Image 3", z=-100, parent=gr)
    c1.addItem(i2)
    c1.addItem(i3)
    
    i1.setMovable(True)
    i2.setMovable(True)
    