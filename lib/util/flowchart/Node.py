# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
#from PySide import QtCore, QtGui
from Terminal import *
from advancedTypes import OrderedDict

class Node(QtCore.QObject):
    def __init__(self, name, terminals=None):
        QtCore.QObject.__init__(self)
        self._name = name
        self._graphicsItem = None
        self.terminals = OrderedDict()
        self.inputs = {}
        self.outputs = {}
        if terminals is None:
            return
        for name, opts in terminals.iteritems():
            self.addTerminal(name, opts)

        
    def nextTerminalName(self, name):
        """Return an unused terminal name"""
        name2 = name
        i = 1
        while name2 in self.terminals:
            name2 = "%s.%d" % (name, i)
            i += 1
        return name2
        
    def addInput(self, name="Input"):
        self.addTerminal(name, ('in',))
        
    def addOutput(self, name="Output"):
        self.addTerminal(name, ('out',))
        
    def addTerminal(self, name, opts):
        name = self.nextTerminalName(name)
        term = Terminal(self, name, opts)
        self.terminals[name] = term
        if opts[0] == 'in':
            self.inputs[name] = term
        else:
            self.outputs[name] = term
        self.graphicsItem().updateTerminals()
        return name, term
        
    def listInputs(self):
        return self.inputs
        
    def listOutputs(self):
        return self.outputs
        
    def process(self, **kargs):
        """Process data through this node. Each named argument supplies data to the corresponding terminal."""
        pass
    
    def graphicsItem(self):
        """Return a (the?) graphicsitem for this node"""
        if self._graphicsItem is None:
            self._graphicsItem = NodeGraphicsItem(self)
        return self._graphicsItem
    
    def __getattr__(self, attr):
        """Return the terminal with the given name"""
        if attr not in self.terminals:
            raise NameError(attr)
        else:
            return self.terminals[attr]
            
    def __getitem__(self, item):
        return getattr(self, item)
            
    def name(self):
        return self._name

    def dependentNodes(self):
        """Return the list of nodes which provide direct input to this node"""
        return set([t.inputTerminal().node() for t in self.listInputs().itervalues()])
        
    def __repr__(self):
        return "<Node %s>" % self.name()
        
    def ctrlWidget(self):
        return None


class NodeGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, node):
        QtGui.QGraphicsItem.__init__(self)
        
        #self.shadow = QtGui.QGraphicsDropShadowEffect()
        #self.shadow.setOffset(5,5)
        #self.shadow.setBlurRadius(10)
        #self.setGraphicsEffect(self.shadow)
        
        self.node = node
        self.setFlags(
            self.ItemIsMovable |
            self.ItemIsSelectable | 
            self.ItemIsFocusable
        )
        bounds = self.boundingRect()
        self.nameItem = QtGui.QGraphicsTextItem(self.node.name(), self)
        self.nameItem.moveBy(bounds.width()/2. - self.nameItem.boundingRect().width()/2., 0)
        self.nameItem.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.updateTerminals()
        
        
    def updateTerminals(self):
        bounds = self.boundingRect()
        self.terminals = {}
        inp = self.node.listInputs()
        dy = bounds.height() / (len(inp)+1)
        y = dy
        for i, t in inp.iteritems():
            item = t.graphicsItem()
            item.setParentItem(self)
            br = self.boundingRect()
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy
        
        out = self.node.listOutputs()
        dy = bounds.height() / (len(out)+1)
        y = dy
        for i, t in out.iteritems():
            item = t.graphicsItem()
            item.setParentItem(self)
            br = self.boundingRect()
            item.setAnchor(bounds.width(), y)
            self.terminals[i] = (t, item)
            y += dy
        
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, 100, 100)
        
    def paint(self, p, *args):
        bounds = self.boundingRect()
        if self.isSelected():
            p.setPen(QtGui.QPen(QtGui.QColor(200, 200, 100)))
            p.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 255)))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150)))
            p.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 200)))
        p.drawRect(bounds)
        
    def mouseMoveEvent(self, ev):
        QtGui.QGraphicsItem.mouseMoveEvent(self, ev)
        for k, t in self.terminals.iteritems():
            t[1].nodeMoved()








        
