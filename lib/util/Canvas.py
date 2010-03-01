# -*- coding: utf-8 -*-

from pyqtgraph.GraphicsView import GraphicsView
from PyQt4 import QtGui, QtCore

class Canvas(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.items = {}
        self.itemList = QtGui.QListWidget()
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
            
        if name is None:
            name = 'item'
        newName = name
        c = 0
        while newName in self.items:
            c += 1
            newName = name + '_%03d' % c
        self.items[newName] = item
        self.itemList.addItem(QtGui.QListWidgetItem(newName))
        return newName
            
    
    def removeItem(self, item):
        self.view.scene().removeItem(item)
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items