# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
#from PySide import QtCore, QtGui
from Terminal import *
from advancedTypes import OrderedDict
from debug import *
import numpy as np
from pyqtgraph.ObjectWorkaround import QObjectWorkaround
from eq import *

class Node(QtCore.QObject):
    def __init__(self, name, terminals=None):
        QtCore.QObject.__init__(self)
        self._name = name
        self._graphicsItem = None
        self.terminals = OrderedDict()
        self._inputs = {}
        self._outputs = {}
        self.exception = None
        if terminals is None:
            return
        for name, opts in terminals.iteritems():
            self.addTerminal(name, **opts)

        
    def nextTerminalName(self, name):
        """Return an unused terminal name"""
        name2 = name
        i = 1
        while name2 in self.terminals:
            name2 = "%s.%d" % (name, i)
            i += 1
        return name2
        
    def addInput(self, name="Input", **args):
        return self.addTerminal(name, io='in', **args)
        
    def addOutput(self, name="Output", **args):
        return self.addTerminal(name, io='out', **args)
        
    def removeTerminal(self, name):
        #print "remove", name
        term = self.terminals[name]
        term.close()
        del self.terminals[name]
        if name in self._inputs:
            del self._inputs[name]
        if name in self._outputs:
            del self._outputs[name]
        self.graphicsItem().updateTerminals()
        
        
    def terminalRenamed(self, term, oldName, newName):
        """Called after a terminal has been renamed"""
        print "node", self, "handling rename.."
        for d in [self.terminals, self._inputs, self._outputs]:
            if oldName not in d:
                continue
            print "  got one"
            d[newName] = d[oldName]
            del d[oldName]
            
        self.graphicsItem().updateTerminals()
        self.emit(QtCore.SIGNAL('terminalRenamed'), term, oldName)
        
    def addTerminal(self, name, **opts):
        name = self.nextTerminalName(name)
        term = Terminal(self, name, **opts)
        self.terminals[name] = term
        if term.isInput():
            self._inputs[name] = term
        elif term.isOutput():
            self._outputs[name] = term
        self.graphicsItem().updateTerminals()
        return term
        
    def inputs(self):
        return self._inputs
        
    def outputs(self):
        return self._outputs
        
    def process(self, **kargs):
        """Process data through this node. Each named argument supplies data to the corresponding terminal."""
        return {}
    
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
        nodes = set()
        for t in self.inputs().itervalues():
            nodes |= set([i.node() for i in t.inputTerminals()])
        return nodes
        #return set([t.inputTerminals().node() for t in self.listInputs().itervalues()])
        
    def __repr__(self):
        return "<Node %s>" % self.name()
        
    def ctrlWidget(self):
        return None

    def setInput(self, **args):
        """Set the values on input terminals. For most nodes, this will happen automatically through Terminal.inputChanged.
        This is normally only used for nodes with no connected inputs."""
        changed = False
        for k, v in args.iteritems():
            term = self._inputs[k]
            oldVal = term.value()
            if not eq(oldVal, v):
                changed = True
            term.setValue(v, process=False)
        if changed:
            self.update()
        
    def inputValues(self):
        vals = {}
        for n, t in self.inputs().iteritems():
            vals[n] = t.value()
        return vals
            
    def outputValues(self):
        vals = {}
        for n, t in self.outputs().iteritems():
            vals[n] = t.value()
        return vals
            
    def connected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is connected elsewhere."""
        pass
    
    def disconnected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is connected elsewhere."""
        pass 
    
    def update(self):
        """Collect all input values, attempt to process new output values, and propagate downstream."""
        #print "processing", self
        vals = self.inputValues()
        #print "  inputs:", vals
        try:
            out = self.process(**vals)
            #print "  output:", out
            if out is not None:
                self.setOutput(**out)
            for n,t in self.inputs().iteritems():
                t.setValueAcceptable(True)
            self.clearException()
        except:
            #printExc( "Exception while processing:")
            for n,t in self.outputs().iteritems():
                t.setValue(None)
            self.setException(sys.exc_info())
        self.emit(QtCore.SIGNAL('outputChanged'))
            
    def setOutput(self, **vals):
        for k, v in vals.iteritems():
            term = self.outputs()[k]
            term.setValue(v)
            targets = term.connections()
            for t in targets:  ## propagate downstream
                if t is term:
                    continue
                t.inputChanged(term)
            term.setValueAcceptable(True)
            
    def setException(self, exc):
        self.exception = exc
        self.recolor()
        
    def clearException(self):
        self.setException(None)
        
    def recolor(self):
        if self.exception is None:
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))
        else:
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(150, 0, 0), 3))

    def saveState(self):
        pos = self.graphicsItem().pos()
        return {'pos': (pos.x(), pos.y())}
        
    def restoreState(self, state):
        pos = state.get('pos', (0,0))
        self.graphicsItem().setPos(*pos)
        
    def saveTerminals(self):
        terms = OrderedDict()
        for n, t in self.terminals.iteritems():
            terms[n] = (t.saveState())
        return terms
        
    def restoreTerminals(self, state):
        for name in self.terminals:
            if name not in state:
                self.removeTerminal(name)
        for name, opts in state.iteritems():
            if name in self.terminals:
                continue
            try:
                self.addTerminal(name, **opts)
            except:
                printExc("Error restoring terminal:")
                
        
    def clearTerminals(self):
        for t in self.terminals.itervalues():
            t.close()
        self.terminals = OrderedDict()
        self._inputs = {}
        self._outputs = {}
        
    def close(self):
        """Cleans up after the node--removes terminals, graphicsItem, widget"""
        self.disconnectAll()
        self.clearTerminals()
        item = self.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        self._graphicsItem = None
        w = self.ctrlWidget()
        if w is not None:
            w.setParent(None)
        self.emit(QtCore.SIGNAL('closed'), self)
            
    def disconnectAll(self):
        for t in self.terminals.values():
            t.disconnectAll()
    

class NodeGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, node):
        QtGui.QGraphicsItem.__init__(self)
        #QObjectWorkaround.__init__(self)
        
        #self.shadow = QtGui.QGraphicsDropShadowEffect()
        #self.shadow.setOffset(5,5)
        #self.shadow.setBlurRadius(10)
        #self.setGraphicsEffect(self.shadow)
        
        self.pen = QtGui.QPen(QtGui.QColor(0,0,0))
        self.brush = QtGui.QBrush(QtGui.QColor(200, 200, 200))
        self.node = node
        self.setFlags(
            self.ItemIsMovable |
            self.ItemIsSelectable | 
            self.ItemIsFocusable |
            self.ItemSendsGeometryChanges
        )
        bounds = self.boundingRect()
        self.nameItem = QtGui.QGraphicsTextItem(self.node.name(), self)
        self.nameItem.moveBy(bounds.width()/2. - self.nameItem.boundingRect().width()/2., 0)
        self.nameItem.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.updateTerminals()
        self.pen = QtGui.QPen(QtGui.QColor(0,0,0))
        
    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setBrush(self, brush):
        self.brush = brush
        self.update()
        
        
    def updateTerminals(self):
        bounds = self.boundingRect()
        self.terminals = {}
        inp = self.node.inputs()
        dy = bounds.height() / (len(inp)+1)
        y = dy
        for i, t in inp.iteritems():
            item = t.graphicsItem()
            item.setParentItem(self)
            br = self.boundingRect()
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy
        
        out = self.node.outputs()
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
        p.setPen(self.pen)
        if self.isSelected():
            p.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 255)))
        else:
            p.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 200)))
        p.drawRect(bounds)
        
    #def mouseMoveEvent(self, ev):
        #QtGui.QGraphicsItem.mouseMoveEvent(self, ev)

    def mousePressEvent(self, ev):
        sel = self.isSelected()
        ret = QtGui.QGraphicsItem.mousePressEvent(self, ev)
        if not sel and self.isSelected():
            #self.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 255)))
            #self.emit(QtCore.SIGNAL('selected'))
            self.update()
        return ret

    #def mouseReleaseEvent(self, ev):
        #ret = QtGui.QGraphicsItem.mouseReleaseEvent(self, ev)
        #return ret

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Delete:
            self.node.close()
            ev.accept()
        else:
            ev.ignore()

    def itemChange(self, change, val):
        if change == self.ItemPositionHasChanged:
            for k, t in self.terminals.iteritems():
                t[1].nodeMoved()
        return QtGui.QGraphicsItem.itemChange(self, change, val)
            



        
