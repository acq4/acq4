# -*- coding: utf-8 -*-

from lib.Manager import getManager
from AnalyzerTemplate import *
from flowchart import *
from PyQt4 import QtGui, QtCore
from DirTreeWidget import DirTreeLoader
from pyqtgraph.PlotWidget import *

class Analyzer(QtGui.QMainWindow):
    def __init__(self, protoDir, parent=None):
        self.protoDir = protoDir
        QtGui.QMainWindow.__init__(self, parent)
        self.ui  =  Ui_MainWindow()
        self.ui.setupUi(self)
        
        self.flowchart = Flowchart()
        self.setCentralWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        
        self.loader = DirTreeLoader(protoDir)
        self.ui.loaderDock.setWidget(self.loader)
        
        self.dockItems = {}
        
        QtCore.QObject.connect(self.ui.loadDataBtn, QtCore.SIGNAL("clicked()"), self.loadData)
        QtCore.QObject.connect(self.ui.addOutputBtn, QtCore.SIGNAL("clicked()"), self.addOutput)
        QtCore.QObject.connect(self.ui.addPlotBtn, QtCore.SIGNAL("clicked()"), self.addPlot)
        QtCore.QObject.connect(self.ui.addCanvasBtn, QtCore.SIGNAL("clicked()"), self.addCanvas)
        QtCore.QObject.connect(self.ui.addTableBtn, QtCore.SIGNAL("clicked()"), self.addTable)
        
        self.resize(1200,800)
        self.show()

    def addOutput(self):
        self.flowchart.addOutput()
        
    def loadData(self):
        data = getManager().currentFile
        self.flowchart.setInput(dataIn=data)
        
    def addPlot(self):
        name = 'Plot'
        i = 0
        while True:
            name2 = '%s_%03d' % (name, i)
            if name2 not in self.dockItems:
                break
            i += 1
        p = PlotWidget()
        d = QtGui.QDockWidget(name2)
        d.setWidget(p)
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
        item = ListItem(name2, d)
        self.dockItems[name2] = item
        self.ui.dockList.addItem(item)
        
        node = self.flowchart.createNode('PlotWidget')
        node.setPlot(p)

    def addCanvas(self):
        pass
    
    def addTable(self):
        pass
    
    
class ListItem(QtGui.QListWidgetItem):
    def __init__(self, name, obj):
        QtGui.QListWidgetItem.__init__(self, name)
        self.obj = obj