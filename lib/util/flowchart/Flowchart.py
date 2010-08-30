# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from Node import *
import functions
from advancedTypes import OrderedDict

#from TreeWidget import *

class Flowchart(Node):
    def __init__(self, terminals, name=None):
        self.outerTerminals = terminals
        self.innerTerminals = {}
        
        ## reverse input/output for internal terminals
        for n, t in terminals.iteritems():
            if t[0] == 'in':
                self.innerTerminals[n] = ('out',) + t[1:]
            else:
                self.innerTerminals[n] = ('in',) + t[1:]
            
            
        if name is None:
            name = "Flowchart"
        Node.__init__(self, name, self.innerTerminals)
        
        
        self.nodes = {}
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
        
    def addNode(self, nodeType, name=None):
        if name is None:
            n = 0
            while True:
                name = "%s.%d" % (nodeType, n)
                if name not in self.nodes:
                    break
                n += 1
                
        node = functions.NODE_LIST[nodeType](name)
            
        item = node.graphicsItem()
        item.setParentItem(self.graphicsItem())
        item.moveBy(len(self.nodes)*150, 0)
        self.nodes[name] = node
        return node
        
    def process(self, **args):
        data = {}  ## Stores terminal:value pairs
        
        ## determine order of operations
        ## order should look like [('p', node1), ('p', node2), ('d', terminal1), ...] 
        ## Each tuple specifies either (p)rocess this node or (d)elete the result from this terminal
        order = self.processOrder()
        print "ORDER:\n", order
        
        ## Record inputs given to process()
        for n, t in self.listOutputs().iteritems():
            data[t] = args[n]
        
        ## process all in order
        for c, arg in order:
            if c == 'p':     ## Process a single node
                node = arg
                outs = node.listOutputs().values()
                ins = node.listInputs().values()
                args = {}
                for inp in ins:
                    inpt = inp.inputTerminal()
                    args[inp.name()] = data[inpt]
                result = node.process(args)
                for out in outs:
                    data[out] = result[out.name()]
            elif c == 'd':   ## delete a terminal result (no longer needed; may be holding a lot of memory)
                del data[arg]
        
        ## Copy to return dict
        result = {}
        for n, t in self.listInputs():
            inpt = t.inputTerminal()
            result[n] = data[inpt]
            
        return result
        
    def processOrder(self):
        """Return the order of operations required to process this chart.
        The order returned should look like [('p', node1), ('p', node2), ('d', terminal1), ...] 
        where each tuple specifies either (p)rocess this node or (d)elete the result from this terminal
        """
        
        ## first collect list of nodes/terminals and their dependencies
        deps = {}
        tdeps = {}
        for name, node in self.nodes.iteritems():
            deps[node] = node.dependentNodes()
            for t in node.listOutputs().itervalues():
                tdeps[t] = t.dependentNodes()
            
        
        ## determine correct node-processing order
        order = self.nodes.values()
        def sortfn(a, b):
            if a in deps[b]:
                return -1
            elif b in deps[a]:
                return 1
            return 0
        order.sort(sortfn)
        
        ## construct list of operations
        ops = [('p', n) for n in order]
        
        ## determine when it is safe to delete terminal values
        for t, nodes in tdeps.iteritems():
            lastInd = 0
            lastNode = None
            for n in nodes:
                if n is self:
                    ind = -1
                else:
                    ind = order.index(n)
                if lastNode is None or ind > lastInd:
                    lastNode = n
                    lastInd = ind
            #tdeps[t] = lastNode
            ops.insert(lastInd+1, ('d', t))
            
        return ops
        

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
       
        for f in functions.NODE_LIST:
            self.nodeCombo.addItem(f)
            
        QtCore.QObject.connect(self.nodeCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.nodeComboChanged)
        QtCore.QObject.connect(self.ctrlList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*,int)'), self.itemChanged)

    def scene(self):
        return self._scene

    def nodeComboChanged(self, ind):
        if ind == 0:
            return
        nodeType = str(self.nodeCombo.currentText())
        self.nodeCombo.setCurrentIndex(0)
        self.chart.addNode(nodeType)

    def itemChanged(self, *args):
        pass

class FlowchartNode(Node):
    pass

