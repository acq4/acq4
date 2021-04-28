# -*- coding: utf-8 -*-
from __future__ import print_function

from six.moves import range

from acq4.util import Qt
import pyqtgraph as pg
import acq4.util.flowchart.EventDetection as FCEventDetection


class ScatterPlotter(Qt.QSplitter):
    ### Draws scatter plots, allows the user to pick which data is used for x and y axes.
    sigClicked = Qt.Signal(object, object)
    
    def __init__(self):
        Qt.QSplitter.__init__(self)
        self.setOrientation(Qt.Qt.Horizontal)
        self.plot = pg.PlotWidget()
        self.addWidget(self.plot)
        self.ctrl = Qt.QWidget()
        self.addWidget(self.ctrl)
        self.layout = Qt.QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.ctrl.setLayout(self.layout)
        
        self.scanList = pg.TreeWidget()
        self.layout.addWidget(self.scanList)
        
        self.filter = FCEventDetection.EventFilter('eventFilter')
        self.layout.addWidget(self.filter.ctrlWidget())
        
        self.xCombo = Qt.QComboBox()
        self.yCombo = Qt.QComboBox()
        self.layout.addWidget(self.xCombo)
        self.layout.addWidget(self.yCombo)
        
        self.columns = []
        self.scans = {}    ## maps scan: (scatterPlotItem, treeItem, valid)
        
        self.xCombo.currentIndexChanged.connect(self.invalidate)
        self.yCombo.currentIndexChanged.connect(self.invalidate)
        self.filter.sigStateChanged.connect(self.invalidate)
        self.scanList.itemChanged.connect(self.itemChanged)

    def itemChanged(self, item, col):
        gi = self.scans[item.scan][0]
        if item.checkState(0) == Qt.Qt.Checked:
            gi.show()
        else:
            gi.hide()
        self.updateAll()

    def invalidate(self):  ## mark all scans as invalid and update
        for s in self.scans:
            self.scans[s][2] = False
        self.updateAll()

    def addScan(self, scanDict):
        plot = pg.ScatterPlotItem(pen=Qt.QPen(Qt.Qt.NoPen), brush=pg.mkBrush((255, 255, 255, 100)))
        self.plot.addItem(plot)
        plot.sigClicked.connect(self.plotClicked)
        
        if not isinstance(scanDict, dict):
            scanDict = {'key':scanDict}
        #print "Adding:", scan.name
        for scan in scanDict.values():
            item = Qt.QTreeWidgetItem([scan.name()])
            item.setCheckState(0, Qt.Qt.Checked)
            item.scan = scan
            self.scanList.addTopLevelItem(item)
            self.scans[scan] = [plot, item, False]
            self.updateScan(scan)
            scan.sigEventsChanged.connect(self.invalidateScan)

    def invalidateScan(self, scan):
        self.scans[scan][2] = False
        self.updateScan(scan)

    def updateScan(self, scan):
        try:
            if self.scans[scan] is True:
                return
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
            pts = [{'pos': (data['output'][i][x], data['output'][i][y]), 'data': (scan, data['output'][i]['SourceFile'], data['output'][i]['fitTime'])} for i in range(len(data['output']))]
            plot.setPoints(pts)
            #print pts
            self.scans[scan][2] = True  ## plot is valid
        except:
            pass
            #debug.printExc("Error updating scatter plot:")
        
    def plotClicked(self, plot, points):
        self.sigClicked.emit(self, points)

    def updateAll(self):
        for s in self.scans:
            if self.scans[s][1].checkState(0) == Qt.Qt.Checked:
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
