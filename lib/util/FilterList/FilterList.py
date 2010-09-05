# -*- coding: utf-8 -*-
from filters import FILTER_LIST
from PyQt4 import QtGui, QtCore
from metaarray import *
from debug import *
import ptime
from TreeWidget import *

#class TreeWidget(QtGui.QTreeWidget):
    #"""Extends QTreeWidget to allow internal drag/drop with widgets in the tree.
    #Also maintains the expanded state of subtrees as they are moved.
    #This class demonstrates the absurd lengths one must go to to make drag/drop work."""
    #def __init__(self, parent=None):
        #QtGui.QTreeWidget.__init__(self, parent)
        #self.setAcceptDrops(True)
        #self.setDragEnabled(True)
        #self.setEditTriggers(QtGui.QAbstractItemView.EditKeyPressed|QtGui.QAbstractItemView.SelectedClicked)

    #def setItemWidget(self, item, col, wid):
        #w = QtGui.QWidget()  ## foster parent / surrogate child widget
        #wid.__pw = w  ## keep an extra reference to the parent
        #exp = item.isExpanded()
        #QtGui.QTreeWidget.setItemWidget(self, item, col, w)
        #l = QtGui.QVBoxLayout()
        #l.setContentsMargins(0,0,0,0)
        #w.setLayout(l)
        #l.addWidget(wid)
        #w.realChild = wid
        #item.setExpanded(False)
        #QtGui.QApplication.instance().processEvents()
        #item.setExpanded(exp)

    #def dropMimeData(self, parent, index, data, action):
        #item = self.currentItem()
        ##db = item.delBtn
        #exp = item.isExpanded()
        #sub = item.child(0)
        #if sub is not None:
            #widget = self.itemWidget(sub, 0).realChild
        #if index > self.invisibleRootItem().indexOfChild(item):
            #index -= 1
        #self.invisibleRootItem().removeChild(item)
        #self.insertTopLevelItem(index, item)
        #if sub is not None:
            #item.addChild(sub)
            #self.setItemWidget(sub, 0, widget)
        #self.setItemWidget(item, 1, db)
        #item.setExpanded(False)
        #QtGui.QApplication.instance().processEvents()
        #item.setExpanded(exp)
        #self.emit(QtCore.SIGNAL('itemMoved'), item, index)
        #return True

class FilterList(QtGui.QWidget):
    """This widget presents a customizable filter chain. The user (or program) can add and remove
    filters from the chain. Each filter defines its own widget of control parameters."""
    
    
    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)
        self.setMinimumWidth(250)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding))
        ## Set up GUI
        self.vl = QtGui.QVBoxLayout()
        self.vl.setSpacing(0)
        self.vl.setContentsMargins(0,0,0,0)
        self.setLayout(self.vl)
        self.filterCombo = QtGui.QComboBox()
        self.filterList = TreeWidget()
        self.filterList.setColumnCount(3)
        self.filterList.setHeaderLabels(['Filter', 'X', 'time'])
        self.filterList.setColumnWidth(0, 200)
        self.filterList.setColumnWidth(1, 20)
        self.filterList.setVerticalScrollMode(self.filterList.ScrollPerPixel)
        self.filterList.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.vl.addWidget(self.filterCombo)
        self.vl.addWidget(self.filterList)
        
        self.filterCombo.addItem("Add..")
        fl = FILTER_LIST.keys()
        fl.sort()
        for k in fl:
            self.filterCombo.addItem(k)
            
        QtCore.QObject.connect(self.filterCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.filterComboChanged)
        QtCore.QObject.connect(self.filterList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.itemChanged)
        QtCore.QObject.connect(self.filterList, QtCore.SIGNAL('itemMoved'), self.emitChange)
        #self.filters = []

    def widgetGroupInterface(self):
        return ('changed', FilterList.saveState, FilterList.restoreState)

    def filterComboChanged(self, ind):
        if ind == 0:
            return
        filterType = str(self.filterCombo.currentText())
        self.filterCombo.setCurrentIndex(0)
        self.addFilter(filterType)
        
    def addFilter(self, filterType, name=None, enabled=True, **opts):
        if filterType not in FILTER_LIST:
            raise Exception("No filter named '%s'. Available filters are: %s" % (str(filterType), str(FILTER_LIST.keys())))
        
        if name is None:
            name = filterType
        filter = FILTER_LIST[filterType](**opts)
        item = QtGui.QTreeWidgetItem([name, ''])
        item.filter = filter
        if enabled:
            item.setCheckState(0, QtCore.Qt.Checked)
        else:
            item.setCheckState(0, QtCore.Qt.Unchecked)
        item.setFlags(
            QtCore.Qt.ItemIsSelectable | 
            QtCore.Qt.ItemIsUserCheckable | 
            QtCore.Qt.ItemIsEnabled | 
            QtCore.Qt.ItemIsDragEnabled |
            QtCore.Qt.ItemIsEditable
        )
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        ctrl = filter.getCtrlGui()
        self.filterList.addTopLevelItem(item)
        delBtn = QtGui.QPushButton('X', self)
        delBtn.item = item
        item.delBtn = delBtn
        QtCore.QObject.connect(delBtn, QtCore.SIGNAL('clicked()'), self.removeFilter)
        self.filterList.setItemWidget(item, 1, delBtn)
        if ctrl is not None:
            item2 = QtGui.QTreeWidgetItem([])
            item2.setFlags(QtCore.Qt.ItemIsEnabled)
            item.addChild(item2)
            self.filterList.setItemWidget(item2, 0, ctrl)
            item.setExpanded(True)
        
        #self.filters.append((filter, item, ctrl))
        QtCore.QObject.connect(filter, QtCore.SIGNAL('delayedChange'), self.emitChange)
        self.emitChange()
        
        
    def removeFilter(self, index=None):
        if index is None:
            item = self.sender().item
        else:
            item = self.filterList.topLevelItem(index)
        QtCore.QObject.disconnect(item.delBtn, QtCore.SIGNAL('clicked()'), self.removeFilter)
        QtCore.QObject.disconnect(item.filter, QtCore.SIGNAL('delayedChange'), self.emitChange)
        self.filterList.invisibleRootItem().removeChild(item)
        self.emitChange()
        
        
    def itemChanged(self, item, col):
        if col == 0:
            self.emitChange()
        
    #def itemMoved(self, *args):
        #f = []
        #for i in range(self.filterList.topLevelItemCount()):
            #item = self.filterList.topLevelItem(i)
            #ind = item.index
            #f.append(self.filters[index])
        
        
    def emitChange(self):
        self.emit(QtCore.SIGNAL('changed'))
    
    def listFilters(self):
        pass
    
    def processData(self, data, x=None):
        """Process data using the chain of filters. If x is specified, then a MetaArray is automatically constructed
        and (data, xvals) is returned."""
        returnX = False
        if x is not None:
            data = MetaArray(data, info=[{'values': x}])
            returnX = True
        
        for i in range(self.filterList.topLevelItemCount()):
            item = self.filterList.topLevelItem(i)
            filter = item.filter
            if item.checkState(0) == QtCore.Qt.Checked:
                try:
                    now = ptime.time()
                    data = filter.processData(data)
                    #print "----------"
                    #print data
                    item.setForeground(0, QtGui.QBrush(QtGui.QColor(0,0,0)))
                    item.setText(2, '%0.2fms'% ((ptime.time()-now)*1e3))
                except:
                    item.setForeground(0, QtGui.QBrush(QtGui.QColor(200,0,0)))
                    printExc("Filter '%s' failed:" % filter.__class__.__name__)
                    
                
        if returnX:
            return data.view(ndarray), data.xvals(0)
        else:
            return data
    
    def saveState(self):
        state = []
        for i in range(self.filterList.topLevelItemCount()):
            item = self.filterList.topLevelItem(i)
            filter = item.filter
            s = {
                'name': str(item.text(0)), 
                'type': filter.__class__.__name__, 
                'enabled': item.checkState(0) == QtCore.Qt.Checked, 
                'expanded': item.isExpanded(),
                'opts': filter.saveState()
            }
            state.append(s)
        return state
    
    def restoreState(self, state):
        for f in state:
            self.addFilter(f['type'], enabled=f['enabled'], name=f['name'], **f['opts'])
    
    
