# -*- coding: utf-8 -*-
import importlib
import weakref

import gc

from pyqtgraph.Qt import QtCore, QT_LIB, QtWidgets
from pyqtgraph.graphicsItems.GridItem import GridItem
from pyqtgraph.graphicsItems.ROI import ROI
from pyqtgraph.graphicsItems.ViewBox import ViewBox
from .CanvasItem import CanvasItem, GroupCanvasItem
from .CanvasManager import CanvasManager

ui_template = importlib.import_module(
    f'.CanvasTemplate_{QT_LIB.lower()}', package=__package__)


translate = QtCore.QCoreApplication.translate


class Canvas(QtWidgets.QWidget):
    
    sigSelectionChanged = QtCore.Signal(object, object)
    sigItemTransformChanged = QtCore.Signal(object, object)
    sigItemTransformChangeFinished = QtCore.Signal(object, object)
    
    def __init__(self, parent=None, allowTransforms=True, hideCtrl=False, name=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.ui = ui_template.Ui_Form()
        self.ui.setupUi(self)
        self.view = ViewBox()
        self.ui.view.setCentralItem(self.view)
        self.itemList = self.ui.itemList
        self.itemList.setSelectionMode(self.itemList.ExtendedSelection)
        self.allowTransforms = allowTransforms
        self.multiSelectBox = SelectBox()
        self.view.addItem(self.multiSelectBox)
        self.multiSelectBox.hide()
        self.multiSelectBox.setZValue(1e6)
        self.ui.mirrorSelectionBtn.hide()
        self.ui.reflectSelectionBtn.hide()
        self.ui.resetTransformsBtn.hide()
        
        self.redirect = None  ## which canvas to redirect items to
        self.items = []
        
        self.view.setAspectLocked(True)
        
        grid = GridItem()
        self.grid = CanvasItem(grid, name='Grid', movable=False)
        self.addItem(self.grid)
        
        self.hideBtn = QtWidgets.QPushButton('>', self)
        self.hideBtn.setFixedWidth(20)
        self.hideBtn.setFixedHeight(20)
        self.ctrlSize = 200
        self.sizeApplied = False
        self.hideBtn.clicked.connect(self.hideBtnClicked)
        self.ui.splitter.splitterMoved.connect(self.splitterMoved)
        
        self.ui.itemList.itemChanged.connect(self.treeItemChanged)
        self.ui.itemList.sigItemMoved.connect(self.treeItemMoved)
        self.ui.itemList.itemSelectionChanged.connect(self.treeItemSelected)
        self.ui.autoRangeBtn.clicked.connect(self.autoRange)
        self.ui.redirectCheck.toggled.connect(self.updateRedirect)
        self.ui.redirectCombo.currentIndexChanged.connect(self.updateRedirect)
        self.multiSelectBox.sigRegionChanged.connect(self.multiSelectBoxChanged)
        self.multiSelectBox.sigRegionChangeFinished.connect(self.multiSelectBoxChangeFinished)
        self.ui.mirrorSelectionBtn.clicked.connect(self.mirrorSelectionClicked)
        self.ui.reflectSelectionBtn.clicked.connect(self.reflectSelectionClicked)
        self.ui.resetTransformsBtn.clicked.connect(self.resetTransformsClicked)
        
        self.resizeEvent()
        if hideCtrl:
            self.hideBtnClicked()
            
        if name is not None:
            self.registeredName = CanvasManager.instance().registerCanvas(self, name)
            self.ui.redirectCombo.setHostName(self.registeredName)
            
        self.menu = QtWidgets.QMenu()
        remAct = QtWidgets.QAction(translate("Context Menu", "Remove item"), self.menu)
        remAct.triggered.connect(self.removeClicked)
        self.menu.addAction(remAct)
        self.menu.remAct = remAct
        self.ui.itemList.contextMenuEvent = self.itemListContextMenuEvent

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
        self.view.autoRange()

    def resizeEvent(self, ev=None):
        if ev is not None:
            super().resizeEvent(ev)
        self.hideBtn.move(self.ui.view.size().width() - self.hideBtn.width(), 0)
        
        if not self.sizeApplied:
            self.sizeApplied = True
            s = min(self.width(), max(100, min(200, self.width()*0.25)))
            s2 = self.width()-s
            self.ui.splitter.setSizes([s2, s])
    
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
                    print("Skipping item", i, i.name)
                    continue
                tree.removeTopLevelItem(li)
            else:
                parent.removeChild(li)
            canvas.addItem(i)

    def reclaimItems(self):
        items = self.items
        self.items = [self.grid]
        items.remove(self.grid)
        
        for i in items:
            i.canvas.removeItem(i)
            self.addItem(i)

    def treeItemChanged(self, item, col):
        try:
            citem = item.canvasItem()
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

        if len(sel) == 0:
            return
            
        multi = len(sel) > 1
        for i in self.items:
            ## updated the selected state of every item
            i.selectionChanged(i in sel, multi)
            
        if len(sel)==1:
            self.multiSelectBox.hide()
            self.ui.mirrorSelectionBtn.hide()
            self.ui.reflectSelectionBtn.hide()
            self.ui.resetTransformsBtn.hide()
        elif len(sel) > 1:
            self.showMultiSelectBox()
        
        self.sigSelectionChanged.emit(self, sel)
        
    def selectedItems(self):
        """
        Return list of all selected canvasItems
        """
        return [item.canvasItem() for item in self.itemList.selectedItems() if item.canvasItem() is not None]
        
    def selectItem(self, item):
        li = item.listItem
        self.itemList.setCurrentItem(li)
        
    def showMultiSelectBox(self):
        ## Get list of selected canvas items
        items = self.selectedItems()
        
        rect = self.view.itemBoundingRect(items[0].graphicsItem())
        for i in items:
            if not i.isMovable():  ## all items in selection must be movable
                return
            br = self.view.itemBoundingRect(i.graphicsItem())
            rect = rect|br
            
        self.multiSelectBox.blockSignals(True)
        self.multiSelectBox.setPos([rect.x(), rect.y()])
        self.multiSelectBox.setSize(rect.size())
        self.multiSelectBox.setAngle(0)
        self.multiSelectBox.blockSignals(False)
        
        self.multiSelectBox.show()
        
        self.ui.mirrorSelectionBtn.show()
        self.ui.reflectSelectionBtn.show()
        self.ui.resetTransformsBtn.show()

    def mirrorSelectionClicked(self):
        for ci in self.selectedItems():
            ci.mirrorY()
        self.showMultiSelectBox()

    def reflectSelectionClicked(self):
        for ci in self.selectedItems():
            ci.mirrorXY()
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
        citem = CanvasItem(item, **opts)
        item._canvasItem = citem
        self.addItem(citem)
        return citem

    def addGroup(self, name, **kargs):
        group = GroupCanvasItem(name=name)
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
        insertLocation = 0
        #print "Inserting node:", name
        
            
        ## determine parent list item where this item should be inserted
        parent = citem.parentItem()
        if parent in (None, self.view.childGroup):
            parent = self.itemList.invisibleRootItem()
        else:
            parent = parent.listItem
        
        ## set Z value above all other siblings if none was specified
        siblings = [parent.child(i).canvasItem() for i in range(parent.childCount())]
        z = citem.zValue()
        if z is None:
            zvals = [i.zValue() for i in siblings]
            if parent is self.itemList.invisibleRootItem():
                if len(zvals) == 0:
                    z = 0
                else:
                    z = max(zvals)+10
            else:
                if len(zvals) == 0:
                    z = parent.canvasItem().zValue()
                else:
                    z = max(zvals)+1
            citem.setZValue(z)
            
        ## determine location to insert item relative to its siblings
        for i in range(parent.childCount()):
            ch = parent.child(i)
            zval = ch.canvasItem().graphicsItem().zValue()  ## should we use CanvasItem.zValue here?
            if zval < z:
                insertLocation = i
                break
            else:
                insertLocation = i+1
                
        node = QtWidgets.QTreeWidgetItem([name])
        flags = node.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsDragEnabled
        if not isinstance(citem, GroupCanvasItem):
            flags = flags & ~QtCore.Qt.ItemIsDropEnabled
        node.setFlags(flags)
        if citem.opts['visible']:
            node.setCheckState(0, QtCore.Qt.Checked)
        else:
            node.setCheckState(0, QtCore.Qt.Unchecked)
        
        node.name = name
        parent.insertChild(insertLocation, node)
        
        citem.name = name
        citem.listItem = node
        node.canvasItem = weakref.ref(citem)
        self.items.append(citem)

        ctrl = citem.ctrlWidget()
        ctrl.hide()
        self.ui.ctrlLayout.addWidget(ctrl)
        
        ## inform the canvasItem that its parent canvas has changed
        citem.setCanvas(self)

        ## Autoscale to fit the first item added (not including the grid).
        if len(self.items) == 2:
            self.autoRange()
            
        return citem

    def treeItemMoved(self, item, parent, index):
        ##Item moved in tree; update Z values
        if parent is self.itemList.invisibleRootItem():
            item.canvasItem().setParentItem(self.view.childGroup)
        else:
            item.canvasItem().setParentItem(parent.canvasItem())
        siblings = [parent.child(i).canvasItem() for i in range(parent.childCount())]
        
        zvals = [i.zValue() for i in siblings]
        zvals.sort(reverse=True)
        
        for i in range(len(siblings)):
            item = siblings[i]
            item.setZValue(zvals[i])
        
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
        if isinstance(item, QtWidgets.QTreeWidgetItem):
            item = item.canvasItem()
            
        if isinstance(item, CanvasItem):
            item.setCanvas(None)
            listItem = item.listItem
            listItem.canvasItem = None
            item.listItem = None
            self.itemList.removeTopLevelItem(listItem)
            self.items.remove(item)
            ctrl = item.ctrlWidget()
            ctrl.hide()
            self.ui.ctrlLayout.removeWidget(ctrl)
            ctrl.setParent(None)
        else:
            if hasattr(item, '_canvasItem'):
                self.removeItem(item._canvasItem)
            else:
                self.view.removeItem(item)
                
        gc.collect()
        
    def clear(self):
        while len(self.items) > 0:
            self.removeItem(self.items[0])

    def addToScene(self, item):
        self.view.addItem(item)
        
    def removeFromScene(self, item):
        self.view.removeItem(item)
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items
        
    def getListItem(self, name):
        return self.items[name]
        
    def itemTransformChanged(self, item):
        self.sigItemTransformChanged.emit(self, item)
    
    def itemTransformChangeFinished(self, item):
        self.sigItemTransformChangeFinished.emit(self, item)
        
    def itemListContextMenuEvent(self, ev):
        self.menuItem = self.itemList.itemAt(ev.pos())
        self.menu.popup(ev.globalPos())
        
    def removeClicked(self):
        for item in self.selectedItems():
            self.removeItem(item)
        self.menuItem = None
        import gc
        gc.collect()


class SelectBox(ROI):
    def __init__(self, scalable=False):
        #QtGui.QGraphicsRectItem.__init__(self, 0, 0, size[0], size[1])
        ROI.__init__(self, [0,0], [1,1])
        center = [0.5, 0.5]
            
        if scalable:
            self.addScaleHandle([1, 1], center, lockAspect=True)
            self.addScaleHandle([0, 0], center, lockAspect=True)
        self.addRotateHandle([0, 1], center)
        self.addRotateHandle([1, 0], center)
