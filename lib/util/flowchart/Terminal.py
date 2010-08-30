# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class Terminal:
    def __init__(self, node, name, opts):
        self._node = node
        self._name = name
        self._isOutput = opts[0]=='out'
        self._connections = {}
        self._graphicsItem = TerminalGraphicsItem(self)
        self.recolor()
        
    def node(self):
        return self._node
        
    def isInput(self):
        return not self._isOutput

    def isOutput(self):
        return self._isOutput
        
    def name(self):
        return self._name
        
    def graphicsItem(self):
        return self._graphicsItem
        
    def isConnected(self):
        return len(self._connections) > 0
        
    def connectedTo(self, term):
        return term in self._connections
        
    def hasInput(self):
        conn = self.extendedConnections()
        for t in conn:
            if t.isOutput():
                return True
        return False        
        
    def inputTerminal(self):
        """Return the terminal that gives input to this one."""
        terms = self.extendedConnections()
        for t in terms:
            if t.isOutput():
                return t
        
    def dependentNodes(self):
        """Return the list of nodes which receive input from this terminal."""
        conn = self.extendedConnections()
        del conn[self]
        return set([t.node() for t in conn])
        
        
    def connectTo(self, term, connectionItem=None):
        if self.connectedTo(term):
            raise Exception('Already connected')
        if term is self:
            raise Exception('Not connecting terminal to self')
        if self.hasInput() and term.hasInput():
            raise Exception('Target terminal already has input')
            
        if term in self.node().terminals.values():
            if self.isOutput() or term.isOutput():
                raise Exception('Can not connect an output back to the same node.')
        
        if connectionItem is None:
            connectionItem = ConnectionItem(self.graphicsItem(), term.graphicsItem())
            self.graphicsItem().scene().addItem(connectionItem)
        self._connections[term] = connectionItem
        term._connections[self] = connectionItem
        
        self.recolor()
        
    def disconnectFrom(self, term):
        if not self.connectedTo(term):
            return
        item = self._connections[term]
        item.scene().removeItem(item)
        del self._connections[term]
        del term._connections[self]
        self.recolor()
        term.recolor()
        
    def recolor(self, color=None, recurse=True):
        if color is None:
            if self.isConnected():
                if self.hasInput():
                    color = QtGui.QColor(100, 200, 100)
                else:
                    color = QtGui.QColor(200, 200, 100)
            else:
                color = QtGui.QColor(255,255,255)
        self.graphicsItem().setBrush(QtGui.QBrush(color))
        
        if recurse:
            for t in self.extendedConnections():
                t.recolor(color, recurse=False)

        
    def __repr__(self):
        return "<Terminal %s.%s>" % (str(self.node().name()), str(self.name()))
        
    def connections(self):
        return self._connections
        
    def extendedConnections(self, terms=None):
        """Return list of terminals (including this one) that are directly or indirectly wired to this."""        
        if terms is None:
            terms = {}
        terms[self] = None
        for t in self._connections:
            if t in terms:
                continue
            terms.update(t.extendedConnections(terms))
        return terms
        
    def __hash__(self):
        return id(self)
        
        
class TerminalGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, term, parent=None):
        self.term = term
        QtGui.QGraphicsItem.__init__(self, parent)
        self.box = QtGui.QGraphicsRectItem(0, 0, 10, 10, self)
        self.label = QtGui.QGraphicsTextItem(self.term.name(), self)
        self.label.scale(0.7, 0.7)
        self.setAcceptHoverEvents(True)
        self.newConnection = None

    def setBrush(self, brush):
        self.box.setBrush(brush)

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
                        raise
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
        self.setZValue(-10)
        
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
            pen = QtGui.QPen(QtGui.QColor(200, 200, 0), 3)
        else:
            pen = QtGui.QPen(QtGui.QColor(0, 0, 0), 1)
        if self.line.pen() != pen:
            self.line.setPen(pen)
