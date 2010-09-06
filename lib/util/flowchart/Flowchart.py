# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
#from PySide import QtCore, QtGui
from Node import *
import functions
from advancedTypes import OrderedDict
from TreeWidget import *

def toposort(deps, nodes=None, seen=None, stack=None):
    """Topological sort. Arguments are:
      deps    dictionary describing dependencies where a:[b,c] means "a depends on b and c"
      nodes   optional, specifies list of starting nodes (these should be the nodes 
              which are not depended on by any other nodes) 
    """
    if nodes is None:
        ## run through deps to find nodes that are not depended upon
        rem = set()
        for dep in deps.itervalues():
            rem |= set(dep)
        nodes = set(deps.keys()) - rem
    if seen is None:
        seen = set()
        stack = []
    sorted = []
    for n in nodes:
        if n in stack:
            raise Exception("Cyclic dependency detected", stack + [n])
        if n in seen:
            continue
        seen.add(n)
        sorted.extend( toposort(deps, deps[n], seen, stack+[n]))
        sorted.append(n)
    return sorted
        

class Flowchart(Node):
    def __init__(self, terminals, name=None):
        if name is None:
            name = "Flowchart"
        Node.__init__(self, name)
            
        self.nodes = {}
        self.connects = []
        self._chartGraphicsItem = FlowchartGraphicsItem(self)
        self._widget = None
        self._scene = None
        
        self.inputNode = Node('Input')
        self.outputNode = Node('Output')
        self.addNode(self.inputNode, 'Input', [-200, 200])
        self.addNode(self.outputNode, 'Output', [600, 200])
            
        for name, opts in terminals.iteritems():
            self.addTerminal(name, opts)
      
        
        
    def addTerminal(self, name, opts):
        name, term = Node.addTerminal(self, name, opts)
        if opts[0] == 'in':
            opts = ('out',) + opts[1:]
            self.inputNode.addTerminal(name, opts)
        else:
            opts = ('in',) + opts[1:]
            self.outputNode.addTerminal(name, opts)

    def createNode(self, nodeType, name=None):
        if name is None:
            n = 0
            while True:
                name = "%s.%d" % (nodeType, n)
                if name not in self.nodes:
                    break
                n += 1
                
        node = functions.NODE_LIST[nodeType](name)
        self.addNode(node, name)
        return node
        
    def addNode(self, node, name, pos=None):
        if pos is None:
            pos = [0, 0]
        item = node.graphicsItem()
        item.setParentItem(self.chartGraphicsItem())
        item.moveBy(*pos)
        self.nodes[name] = node
        self.widget().addNode(node)
        
    def arrangeNodes(self):
        
        pass
        
    def internalTerminal(self, term):
        """If the terminal belongs to the external Node, return the corresponding internal terminal"""
        if term.node() is self:
            if term.isInput():
                return self.inputNode[term.name()]
            else:
                return self.outputNode[term.name()]
                
        else:
            return term
        
    def connect(self, term1, term2):
        """Connect two terminals together within this flowchart."""
        term1 = self.internalTerminal(term1)
        term2 = self.internalTerminal(term2)
        term1.connectTo(term2)
        
        
    def process(self, **args):
        data = {}  ## Stores terminal:value pairs
        
        ## determine order of operations
        ## order should look like [('p', node1), ('p', node2), ('d', terminal1), ...] 
        ## Each tuple specifies either (p)rocess this node or (d)elete the result from this terminal
        order = self.processOrder()
        print "ORDER:\n", order
        
        ## Record inputs given to process()
        for n, t in self.inputNode.listOutputs().iteritems():
            data[t] = args[n]
        
        ## process all in order
        for c, arg in order:
            
            if c == 'p':     ## Process a single node
                print "process:", arg
                node = arg
                outs = node.listOutputs().values()
                ins = node.listInputs().values()
                print "  ", outs, ins
                args = {}
                for inp in ins:
                    inpt = inp.inputTerminal()
                    
                    if inpt is None:
                        continue
                    args[inp.name()] = data[inpt]
                if node is self.outputNode:
                    return args
                else:
                    result = node.process(**args)
                    for out in outs:
                        print "    Output:", out, out.name()
                        #print out.name()
                        try:
                            data[out] = result[out.name()]
                        except:
                            print out, out.name()
                            raise
            elif c == 'd':   ## delete a terminal result (no longer needed; may be holding a lot of memory)
                del data[arg]
        
        ## Copy to return dict
        #result = {}
        #for n, t in self.outputNode.listInputs().iteritems():
            ##inpt = t.inputTerminal()
            #result[n] = data[t]
            
        #return result
        
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
            
        print "DEPS:", deps
        ## determine correct node-processing order
        #deps[self] = []
        order = toposort(deps)[1:]
        print "ORDER1:", order
        
        ## construct list of operations
        ops = [('p', n) for n in order]
        
        ## determine when it is safe to delete terminal values
        dels = []
        for t, nodes in tdeps.iteritems():
            lastInd = 0
            lastNode = None
            for n in nodes:
                if n is self:
                    lastInd = None
                    break
                else:
                    ind = order.index(n)
                if lastNode is None or ind > lastInd:
                    lastNode = n
                    lastInd = ind
            #tdeps[t] = lastNode
            if lastInd is not None:
                dels.append((lastInd+1, t))
        dels.sort(lambda a,b: cmp(b[0], a[0]))
        for i, t in dels:
            ops.insert(i, ('d', t))
            
        return ops
        

    def chartGraphicsItem(self):
        """Return the graphicsItem which displays the internals of this flowchart.
        (graphicsItem() still returns the external-view item)"""
        return self._chartGraphicsItem
        
    def widget(self):
        if self._widget is None:
            self._widget = FlowchartWidget(self)
            self.scene = self._widget.scene()
            #self._scene = QtGui.QGraphicsScene()
            #self._widget.setScene(self._scene)
            self.scene.addItem(self.chartGraphicsItem())
        return self._widget

class FlowchartGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, chart):
        QtGui.QGraphicsItem.__init__(self)
        self.chart = chart
        self.updateTerminals()
        
    def updateTerminals(self):
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
        return QtCore.QRectF()
        
    def paint(self, p, *args):
        pass
        #p.drawRect(self.boundingRect())
    

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
        self.ctrlList = TreeWidget()
        self.ctrlList.setColumnCount(1)
        #self.ctrlList.setHeaderLabels(['Filter', 'X', 'time'])
        self.ctrlList.setColumnWidth(0, 200)
        #self.ctrlList.setColumnWidth(1, 20)
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
        
        self.nodeCombo.addItem("Add Node..")
       
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
        self.chart.createNode(nodeType)

    def itemChanged(self, *args):
        pass
    
    def addNode(self, node):
        ctrl = node.ctrlWidget()
        if ctrl is None:
            return
        item = QtGui.QTreeWidgetItem([node.name(), '', ''])
        self.ctrlList.addTopLevelItem(item)
        item2 = QtGui.QTreeWidgetItem()
        item.addChild(item2)
        self.ctrlList.setItemWidget(item2, 0, ctrl)
        

class FlowchartNode(Node):
    pass

