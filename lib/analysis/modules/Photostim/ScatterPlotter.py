# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg
import pyqtgraph.TreeWidget as TreeWidget
import flowchart.library.EventDetection as FCEventDetection
import debug

class ScatterPlotter(QtGui.QSplitter):
    ### Draws scatter plots, allows the user to pick which data is used for x and y axes.
    sigClicked = QtCore.Signal(object, object)
    
    def __init__(self):
        QtGui.QSplitter.__init__(self)
        self.setOrientation(QtCore.Qt.Horizontal)
        self.plot = pg.PlotWidget()
        self.addWidget(self.plot)
        self.ctrl = QtGui.QWidget()
        self.addWidget(self.ctrl)
        self.layout = QtGui.QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.ctrl.setLayout(self.layout)
        
        self.scanList = TreeWidget.TreeWidget()
        self.layout.addWidget(self.scanList)
        
        self.filter = FCEventDetection.EventFilter('eventFilter')
        self.layout.addWidget(self.filter.ctrlWidget())
        
        self.xCombo = QtGui.QComboBox()
        self.yCombo = QtGui.QComboBox()
        self.layout.addWidget(self.xCombo)
        self.layout.addWidget(self.yCombo)
        
        self.columns = []
        self.scans = {}    ## maps scan: (scatterPlotItem, treeItem)
        
        self.xCombo.currentIndexChanged.connect(self.updateAll)
        self.yCombo.currentIndexChanged.connect(self.updateAll)
        self.filter.sigStateChanged.connect(self.updateAll)
        self.scanList.itemChanged.connect(self.itemChanged)

    def itemChanged(self, item, col):
        gi = self.scans[item.scan][0]
        if item.checkState(0) == QtCore.Qt.Checked:
            gi.show()
        else:
            gi.hide()



    def addScan(self, scanDict):
        plot = pg.ScatterPlotItem(pen=QtGui.QPen(QtCore.Qt.NoPen), brush=pg.mkBrush((255, 255, 255, 100)))
        self.plot.addDataItem(plot)
        
        if not isinstance(scanDict, dict):
            scanDict = {'key':scanDict}
        #print "Adding:", scan.name
        for scan in scanDict.values():
            item = QtGui.QTreeWidgetItem([scan.name()])
            item.setCheckState(0, QtCore.Qt.Checked)
            item.scan = scan
            self.scanList.addTopLevelItem(item)
            self.scans[scan] = (plot, item)
            self.updateScan(scan)
            scan.sigEventsChanged.connect(self.updateScan)
    
    def updateScan(self, scan):
        try:
            self.updateColumns(scan)
            x, y = self.getAxes()
            plot = self.scans[scan][0]
            data = scan.getAllEvents()
            if data is None:
                plot.setPoints([])
                return
                
            data = self.filter.process(data, {})
            #print "scatter plot:", len(data['output']), "pts"
            
            ### TODO: if 'fitTime' is not available, we should fall back to 'index'
            pts = [{'pos': (data['output'][i][x], data['output'][i][y]), 'data': (scan, data['output'][i]['SourceFile'], data['output'][i]['fitTime'])} for i in xrange(len(data['output']))]
            plot.setPoints(pts)
            #print pts
            plot.sigClicked.connect(self.plotClicked)
        except:
            pass
            #debug.printExc("Error updating scatter plot:")
        
    def plotClicked(self, plot, points):
        self.sigClicked.emit(self, points)
    
    def updateAll(self):
        for s in self.scans:
            if self.scans[s][1].checkState(0) == QtCore.Qt.Checked:
                self.updateScan(s)
    
    def updateColumns(self, scan):
        ev = scan.getAllEvents()
        if ev is None:
            return
        cols = ev.dtype.names
        for c in cols:
            if c not in self.columns:
                self.xCombo.addItem(c)
                self.yCombo.addItem(c)
        for c in self.columns:
            if c not in cols:
                ind = self.xCombo.findText(c)
                self.xCombo.removeItem(ind)
                self.yCombo.removeItem(ind)
        self.columns = cols
    
    def getAxes(self):
        return str(self.xCombo.currentText()), str(self.yCombo.currentText())
