# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from Terminal import *

class Node(QtCore.QObject):
    def __init__(self, name, terminals):
        QtCore.QObject.__init__(self)
        self._name = name
        self.terminals = terminals
        self.inputs = {}
        self.outputs = {}
        for name, term in terminals.iteritems():
            if not isinstance(term, Terminal):
                try:
                    term = Terminal(self, name, term)
                    terminals[name] = term
                except:
                    raise Exception('Cannot build Terminal from arguments')
            
            if term.isInput():
                self.inputs[name] = term
            else:
                self.outputs[name] = term
        
    def listInputs(self):
        return self.inputs
        
    def listOutputs(self):
        return self.outputs
        
    def process(self, **kargs):
        """Process data through this node. Each named argument supplies data to the corresponding terminal."""
        pass
    
    def graphicsItem(self):
        """Return a (the?) graphicsitem for this node"""
        return NodeGraphicsItem(self)
    
    def __getattr__(self, attr):
        """Return the terminal with the given name"""
        if attr not in self.terminals:
            raise NameError()
        else:
            return self.terminal[attr]
            
    def name(self):
        return self._name

    def getDependencyTree(self):
        tree = {}
        for n, t in self.listInputs().iteritems():
            inp = t.getInputTerminal()
            tree[n] = (inp, inp.node().getDependencyTree())
        return tree


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








        
