# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from Node import *
import functions
from advancedTypes import OrderedDict

#from TreeWidget import *

class Flowchart(Node):
    def __init__(self, terminals):
        self.outerTerminals = terminals
        self.innerTerminals = {}
        
        ## reverse input/output for internal terminals
        for n, t in terminals.iteritems():
            if t[0] == 'in':
                self.innerTerminals[n] = ('out',) + t[1:]
            else:
                self.innerTerminals[n] = ('in',) + t[1:]
            
        Node.__init__(self, None, self.innerTerminals)
        
        
        self.nodes = []
        self.connects = []
        self._graphicsItem = FlowchartGraphicsItem(self)
        self._widget = None
        self._scene = None
        
        #self.terminals = terminals
        #self.inputs = {}
        #self.outputs = {}
        #for name, term in terminals.iteritems():
            #if not isinstance(term, Terminal):
                #try:
                    #term = Terminal(self, name, term)
                    #terminals[name] = term
                #except:
                    #raise Exception('Cannot build Terminal from arguments')
            
            #if term.isInput():
                #self.inputs[name] = term
            #else:
                #self.outputs[name] = term
        
    def addNode(self, node):
        item = node.graphicsItem()
        item.setParentItem(self.graphicsItem())
        item.moveBy(len(self.nodes)*150, 0)
        self.nodes.append(node)
        
    def process(self, **args):
        order = []
        depTree = self.getDependencyTree()
        print depTree
        
        pass


    def graphicsItem(self):
        return self._graphicsItem
        
    def widget(self):
        if self._widget is None:
            self._widget = FlowchartWidget(self)
            self.scene = self._widget.scene()
            #self._scene = QtGui.QGraphicsScene()
            #self._widget.setScene(self._scene)
            self.scene.addItem(self.graphicsItem())
        return self._widget

class FlowchartGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, chart):
        QtGui.QGraphicsItem.__init__(self)
        self.chart = chart
        self.terminals = {}
        bounds = self.boundingRect()
        inp = self.chart.listInputs()
        dy = bounds.height() / (len(inp)+1)
        y = dy
        for n, t in inp.iteritems():
            item = t.graphicsItem()
            self.terminals[n] = item
            item.setParentItem(self)
            item.setAnchor(bounds.width(), y)
            y += dy
        out = self.chart.listOutputs()
        dy = bounds.height() / (len(out)+1)
        y = dy
        for n, t in out.iteritems():
            item = t.graphicsItem()
            self.terminals[n] = item
            item.setParentItem(self)
            item.setAnchor(0, y)
            y += dy
        
        
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, 500, 500)
        
    def paint(self, p, *args):
        p.drawRect(self.boundingRect())
    

class FlowchartWidget(QtGui.QSplitter):
    def __init__(self, chart, *args):
        QtGui.QSplitter.__init__(self, *args)
        self.chart = chart
        self.setMinimumWidth(250)
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding))
        
        self.leftWidget = QtGui.QWidget()
        self.vl = QtGui.QVBoxLayout()
        self.vl.setSpacing(0)
        self.vl.setContentsMargins(0,0,0,0)
        self.leftWidget.setLayout(self.vl)
        self.nodeCombo = QtGui.QComboBox()
        self.ctrlList = QtGui.QTreeWidget()
        self.ctrlList.setColumnCount(3)
        self.ctrlList.setHeaderLabels(['Filter', 'X', 'time'])
        self.ctrlList.setColumnWidth(0, 200)
        self.ctrlList.setColumnWidth(1, 20)
        self.ctrlList.setVerticalScrollMode(self.ctrlList.ScrollPerPixel)
        self.ctrlList.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.vl.addWidget(self.nodeCombo)
        self.vl.addWidget(self.ctrlList)
        
        self.addWidget(self.leftWidget)
        self.view = QtGui.QGraphicsView()
        self.addWidget(self.view)
        self._scene = QtGui.QGraphicsScene()
        self.view.setScene(self._scene)
        self.setSizes([200, 1000])
        
        self.nodeCombo.addItem("Add..")
        fl = functions.NODE_LIST
        self.fl = OrderedDict(fl)
        for f in fl:
            self.nodeCombo.addItem(f[0])
            
        QtCore.QObject.connect(self.nodeCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.nodeComboChanged)
        QtCore.QObject.connect(self.ctrlList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.itemChanged)

    def scene(self):
        return self._scene

    def nodeComboChanged(self, ind):
        if ind == 0:
            return
        nodeType = str(self.nodeCombo.currentText())
        self.nodeCombo.setCurrentIndex(0)
        self.chart.addNode(self.fl[nodeType]())

    def itemChanged(self, *args):
        pass

class FlowchartNode(Node):
    pass

