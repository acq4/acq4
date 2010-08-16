# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

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



class NodeGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, node):
        QtGui.QGraphicsItem.__init__(self)
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


class Terminal:
    def __init__(self, node, name, *args):
        self.node = node
        self._name = name
        self._isOutput = args[0]=='out'
        self._connections = {}
        
    def isInput(self):
        return not self._isOutput

    def isOutput(self):
        return self._isOutput
        
    def name(self):
        return self._name
        
    def graphicsItem(self):
        return TerminalGraphicsItem(self)
        
    def isConnected(self):
        return len(self._connections) > 0
        
    def connectedTo(self, term):
        return term in self._connections
        
    def hasInput(self):
        
        
    def connectTo(self, term, graphicsItem=None):
        if self.connectedTo(term):
            raise Exception('Already connected')
        if term is self:
            raise Exception('Not connecting terminal to self')
        if self.isOutput() and term.hasInput():
            raise Exception('Target terminal already has input')
        if term.isOutput() and self.isOutput():
            raise Exception('Can not connect two outputs.')
        if term.isOutput() and self.hasInput():
            raise Exception('Source terminal already has input')
            
        if term in self.node.terminals.values():
            if self.isOutput() or term.isOutput():
                raise Exception('Can not connect an output back to the same node.')
        
        if graphicsItem is None:
            graphicsItem = Connection(self, term)
        self._connections[term] = graphicsItem
        term._connections[self] = graphicsItem
        print "connect", self, term
        
    def disconnectFrom(self, term):
        if not self.connectedTo(term):
            return
        item = self._connections[term]
        item.scene().removeItem(item)
        del self._connections[term]
        del term._connections[self]
        
    def __repr__(self):
        return self.node.name() + "." + self.name()
        
    def connections(self):
        return self._connections
        
        
class TerminalGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, term, parent=None):
        self.term = term
        QtGui.QGraphicsItem.__init__(self, parent)
        self.box = QtGui.QGraphicsRectItem(0, 0, 10, 10, self)
        self.label = QtGui.QGraphicsTextItem(self.term.name(), self)
        self.label.scale(0.7, 0.7)
        self.setAcceptHoverEvents(True)
        self.newConnection = None


    def disconnect(self, target):
        self.term.disconnectFrom(target.term)

    def boundingRect(self):
        br = self.box.mapRectToParent(self.box.boundingRect())
        lr = self.label.mapRectToParent(self.label.boundingRect())
        return br | lr
        
    def paint(self, p, *args):
        pass
        
    def setAnchor(self, x, y):
        pos = QtCore.QPointF(x, y)
        self.anchorPos = pos
        br = self.box.mapRectToParent(self.box.boundingRect())
        lr = self.label.mapRectToParent(self.label.boundingRect())
        
        
        if self.term.isInput():
            self.box.setPos(pos.x(), pos.y()-br.height()/2.)
            self.label.setPos(pos.x() + br.width(), pos.y() - lr.height()/2.)
        else:
            self.box.setPos(pos.x()-br.width(), pos.y()-br.height()/2.)
            self.label.setPos(pos.x()-br.width()-lr.width(), pos.y()-lr.height()/2.)
            
    def mousePressEvent(self, ev):
        ev.accept()
        
    def mouseMoveEvent(self, ev):
        if self.newConnection is None:
            self.newConnection = ConnectionItem(self)
            self.scene().addItem(self.newConnection)
        self.newConnection.setTarget(ev.scenePos())
        
    def mouseReleaseEvent(self, ev):
        if self.newConnection is not None:
            items = self.scene().items(ev.scenePos())
            gotTarget = False
            for i in items:
                if isinstance(i, TerminalGraphicsItem):
                    self.newConnection.setTarget(i)
                    try:
                        self.term.connectTo(i.term, self.newConnection)
                        gotTarget = True
                    except:
                        pass
                    break
            
            if not gotTarget:
                self.scene().removeItem(self.newConnection)
            self.newConnection = None
        
    def hoverEnterEvent(self, ev):
        self.hover = True
        
    def hoverLeaveEvent(self, ev):
        self.hover = False
        
    def connectPoint(self):
        return self.box.sceneBoundingRect().center()

    def nodeMoved(self):
        for t, item in self.term.connections().iteritems():
            item.updateLine()

class ConnectionItem(QtGui.QGraphicsItem):
    def __init__(self, source, target=None):
        QtGui.QGraphicsItem.__init__(self)
        self.setFlags(
            self.ItemIsSelectable | 
            self.ItemIsFocusable
        )
        self.source = source
        self.target = target
        self.line = QtGui.QGraphicsLineItem(self)
        self.updateLine()
        
    def setTarget(self, target):
        self.target = target
        self.updateLine()
    
    def updateLine(self):
        start = self.source.connectPoint()
        if isinstance(self.target, TerminalGraphicsItem):
            stop = self.target.connectPoint()
        elif isinstance(self.target, QtCore.QPointF):
            stop = self.target
        else:
            return
        self.line.setLine(start.x(), start.y(), stop.x(), stop.y())

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Delete:
            self.source.disconnect(self.target)
            ev.accept()
        else:
            ev.ignore()
        
    def boundingRect(self):
        return self.line.boundingRect()
        
    def paint(self, p, *args):
        if self.isSelected():
            self.line.setPen(QtGui.QPen(QtGui.QColor(100, 100, 0)))
        else:
            self.line.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))


class GraphicsLineEdit(QtGui.QGraphicsTextItem):
    """Extends QGraphicsTextItem to mimic the behavior of QLineEdit"""
    def __init__(self, text=None):
        QtGui.QGraphicsTextItem.__init__(self, text)
        

        
