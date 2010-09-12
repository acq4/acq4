# -*- coding: utf-8 -*-

from lib.Manager import getManager
from AnalyzerTemplate import *
from flowchart import *
from PyQt4 import QtGui, QtCore
from DirTreeWidget import DirTreeLoader
from pyqtgraph.PlotWidget import *
import configfile

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
        self.loader.save = self.saveProtocol
        self.loader.new = self.newProtocol
        self.loader.load = self.loadProtocol
        self.ui.loaderDock.setWidget(self.loader)
        
        self.dockItems = {}
        
        QtCore.QObject.connect(self.ui.loadDataBtn, QtCore.SIGNAL("clicked()"), self.loadData)
        QtCore.QObject.connect(self.ui.addOutputBtn, QtCore.SIGNAL("clicked()"), self.addOutput)
        QtCore.QObject.connect(self.ui.addPlotBtn, QtCore.SIGNAL("clicked()"), self.addPlot)
        QtCore.QObject.connect(self.ui.addCanvasBtn, QtCore.SIGNAL("clicked()"), self.addCanvas)
        QtCore.QObject.connect(self.ui.addTableBtn, QtCore.SIGNAL("clicked()"), self.addTable)
        
        self.resize(1200,800)
        self.show()

    def saveProtocol(self, handle):
        state = {'docks': {}}
        for name, d in self.dockItems.iteritems():
            state['docks'][name] = {'type': d['type'], 'state': d['widget'].saveState()}
        state['window'] = str(self.saveState().toPercentEncoding())
        state['flowchart'] = self.flowchart.saveState()
        configfile.writeConfigFile(state, handle.name())
        return True
        
    def newProtocol(self):
        for name, d in self.dockItems.iteritems():
            self.removeDockWidget(d['dock'])
            d['dock'].setObjectName('')
        self.ui.dockList.clear()
        self.flowchart.clear()
        self.flowchart.addInput('dataIn')
        self.dockItems = {}
        
        return True
    
    def loadProtocol(self, handle):
        self.newProtocol()
        state = configfile.readConfigFile(handle.name())
        
        ## restore flowchart
        self.flowchart.restoreState(state['flowchart'])
        
        ## recreate docks
        for name, d in state['docks'].iteritems():
            fn = getattr(self, 'add'+d['type'])
            fn(name, d.get('state', None))
        
        ## restore dock positions
        self.restoreState(QtCore.QByteArray.fromPercentEncoding(state['window']))
        
        
        return True
        


    def addOutput(self):
        self.flowchart.addOutput()
        
    def loadData(self):
        data = getManager().currentFile
        self.flowchart.setInput(dataIn=data)
        
    def addPlot(self, name=None, state=None):
        if name is None:
            name = 'Plot'
            i = 0
            while True:
                name2 = '%s_%03d' % (name, i)
                if name2 not in self.dockItems:
                    break
                i += 1
            name = name2
        
        p = PlotWidget(name=name)
        d = QtGui.QDockWidget(name)
        d.setObjectName(name)
        d.setWidget(p)
        
        if state is not None:
            p.restoreState(state)
        
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
        item = ListItem(name, d)
        self.dockItems[name] = {'type': 'Plot', 'listItem': item, 'dock': d, 'widget': p}
        self.ui.dockList.addItem(item)
        
        nodes = self.flowchart.nodes()
        #print name, nodes
        if name in nodes:
            node = nodes[name]
        else:
            node = self.flowchart.createNode('PlotWidget', name=name)
        node.setPlot(p)

    def addCanvas(self):
        pass
    
    def addTable(self):
        pass
    
    
class ListItem(QtGui.QListWidgetItem):
    def __init__(self, name, obj):
        QtGui.QListWidgetItem.__init__(self, name)
        #self.obj = weakref.ref(obj)