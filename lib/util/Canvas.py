# -*- coding: utf-8 -*-

from pyqtgraph.GraphicsView import GraphicsView
from PyQt4 import QtGui, QtCore

class Canvas(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.items = {}
        self.scans = {}
        self.itemList = QtGui.QTreeWidget()
        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)
        self.view = GraphicsView()
        self.layout.addWidget(self.view)
        self.layout.addWidget(self.itemList)
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
    def addItem(self, item, pos, z=0, scale=None, name=None):
        """Add a new item to the scene at pos. """
        if scale is None:
            scale = [1, 1]
        
        self.view.scene().addItem(item)
        item.resetTransform()
        item.setPos(QtCore.QPointF(pos[0], pos[1]))
        item.scale(scale[0], scale[1])
        item.setZValue(z)
        
        ## Autoscale to fit the first item added.
        if len(self.items) == 0:
            self.view.setRange(item.mapRectToScene(item.boundingRect()))
            
        if isinstance(name, basestring):
            name = [name]
            
        if name is None:
            name = ['item']
           
        newname = tuple(name)
        c=0
        while newname in self.items:
            c += 1
            newname = tuple(name[:-1]) + (name[-1] + '_%03d' %c,)
        name = newname
            
        currentNode = self.itemList.invisibleRootItem()
        for n in name:
            nextnode = None
            for x in range(currentNode.childCount()):
                if n == currentNode.child(x).text(0):
                    nextnode = currentNode.child(x)
            if nextnode == None:
                currentNode.addChild(QtGui.QTreeWidgetItem([n]))
                nextnode = currentNode.child(currentNode.childCount() - 1)
            currentNode = nextnode
                                          
        self.items[tuple(name)] = item
        return name
            
    
    def removeItem(self, item):
        self.view.scene().removeItem(item)
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items