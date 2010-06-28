# -*- coding: utf-8 -*-
from filters import FILTER_LIST
from PyQt4 import QtGui, QtCore
from metaarray import *
from debug import *
import ptime

class FilterList(QtGui.QWidget):
    """This widget presents a customizable filter chain. The user (or program) can add and remove
    filters from the chain. Each filter defines its own widget of control parameters."""
    
    
    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)
        self.setMinimumWidth(200)
        
        ## Set up GUI
        self.vl = QtGui.QVBoxLayout()
        self.setLayout(self.vl)
        self.filterCombo = QtGui.QComboBox()
        self.filterList = QtGui.QTreeWidget()
        self.filterList.setColumnCount(2)
        self.filterList.setHeaderLabels(['Filter', 'time'])
        self.filterList.setDragDropMode(self.filterList.InternalMove)
        self.vl.addWidget(self.filterCombo)
        self.vl.addWidget(self.filterList)
        
        self.filterCombo.addItem("Add..")
        fl = FILTER_LIST.keys()
        fl.sort()
        for k in fl:
            self.filterCombo.addItem(k)
            
        QtCore.QObject.connect(self.filterCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.filterComboChanged)
        QtCore.QObject.connect(self.filterList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.itemChanged)
        self.filters = []
        
    def filterComboChanged(self, ind):
        if ind == 0:
            return
        filterType = str(self.filterCombo.currentText())
        self.filterCombo.setCurrentIndex(0)
        self.addFilter(filterType)
        
    def addFilter(self, filterType, opts=None):
        if filterType not in FILTER_LIST:
            raise Exception("No filter named '%s'. Available filters are: %s" % (str(filterType), str(FILTER_LIST.keys())))
        
        filter = FILTER_LIST[filterType]()
        item = QtGui.QTreeWidgetItem([filterType, ''])
        item.setCheckState(0, QtCore.Qt.Checked)
        item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsDragEnabled)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        ctrl = filter.getCtrlGui()
        self.filterList.addTopLevelItem(item)
        if ctrl is not None:
            item2 = QtGui.QTreeWidgetItem([])
            item2.setFlags(QtCore.Qt.ItemIsEnabled)
            item.addChild(item2)
            self.filterList.setItemWidget(item2, 0, ctrl)
            item.setExpanded(True)
        
        self.filters.append((filter, item, ctrl))
        QtCore.QObject.connect(filter, QtCore.SIGNAL('delayedChange'), self.emitChange)
        self.emitChange()
        
    def itemChanged(self, item, col):
        if col == 0:
            self.emitChange()
        
    def emitChange(self):
        self.emit(QtCore.SIGNAL('changed'))
    
    def removeFilter(self, index=None):
        pass
    
    def listFilters(self):
        pass
    
    def processData(self, data, x=None):
        """Process data using the chain of filters. If x is specified, then a MetaArray is automatically constructed
        and (data, xvals) is returned."""
        returnX = False
        if x is not None:
            data = MetaArray(data, info=[{'values': x}])
            returnX = True
        
        for filter, item, ctrl in self.filters:
            if item.checkState(0) == QtCore.Qt.Checked:
                try:
                    now = ptime.time()
                    data = filter.processData(data)
                    item.setForeground(0, QtGui.QBrush(QtGui.QColor(0,0,0)))
                    item.setText(1, '%0.2fms'% ((ptime.time()-now)*1e3))
                except:
                    item.setForeground(0, QtGui.QBrush(QtGui.QColor(200,0,0)))
                    printExc("Filter '%s' failed:" % filter.__class__.__name__)
                    
                
        if returnX:
            return data.view(ndarray), data.xvals(0)
        else:
            return data
    
    def saveState(self):
        pass
    
    def restoreState(self, state):
        pass
    
    
