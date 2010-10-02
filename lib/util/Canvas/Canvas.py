# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import sys, os
    md = os.path.dirname(os.path.abspath(__file__))
    sys.path = [os.path.dirname(md)] + sys.path
    print md
    
from CanvasTemplate import *
from pyqtgraph.GraphicsView import GraphicsView
import pyqtgraph.graphicsItems as graphicsItems
from PyQt4 import QtGui, QtCore

class Canvas(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.view = self.ui.view
        self.itemList = self.ui.itemList
        
        self.items = {}
        self.scans = {}
        #self.itemList = QtGui.QTreeWidget()
        #self.layout = QtGui.QHBoxLayout()
        #self.setLayout(self.layout)
        #self.view = GraphicsView()
        import sys
        if 'linux' in sys.platform.lower():
            self.view.useOpenGL(False)
        #self.layout.addWidget(self.view)
        #self.layout.addWidget(self.itemList)
        
        self.view.enableMouse()
        self.view.setAspectLocked(True)
        
        self.grid = graphicsItems.GridItem(self.view)
        self.view.addItem(self.grid)
        self.grid.hide()
        
        self.hideBtn = QtGui.QPushButton('>', self)
        self.hideBtn.setFixedWidth(20)
        self.hideBtn.setFixedHeight(20)
        self.ctrlSize = 200
        self.connect(self.hideBtn, QtCore.SIGNAL('clicked()'), self.hideBtnClicked)
        self.connect(self.ui.splitter, QtCore.SIGNAL('splitterMoved(int, int)'), self.splitterMoved)
        self.connect(self.ui.gridCheck, QtCore.SIGNAL('stateChanged(int)'), self.gridCheckChanged)
        self.resizeEvent()

    def splitterMoved(self):
        self.resizeEvent()

    def hideBtnClicked(self):
        ctrlSize = self.ui.splitter.sizes()[1]
        if ctrlSize == 0:
            cs = self.ctrlSize
            w = self.ui.splitter.size().width()
            if cs > w:
                cs = w - 20
            self.ui.splitter.setSizes([w-cs, cs])
            self.hideBtn.setText('>')
        else:
            self.ctrlSize = ctrlSize
            self.ui.splitter.setSizes([100, 0])
            self.hideBtn.setText('<')
        self.resizeEvent()

    def resizeEvent(self, ev=None):
        if ev is not None:
            QtGui.QWidget.resizeEvent(self, ev)
        self.hideBtn.move(self.view.size().width() - self.hideBtn.width(), 0)

    def gridCheckChanged(self, v):
        if self.ui.gridCheck.isChecked():
            self.grid.show()
        else:
            self.grid.hide()

    def addItem(self, item, pos=None, z=0, scale=None, name=None):
        """Add a new item to the scene at pos. """
        if scale is None:
            scale = [1, 1]
        if pos is None:
            pos = [0,0]
        
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
            
    def addImage(self, img, **opts):
        item = graphicsItems.ImageItem(img)
        name = self.addItem(item, **opts)
        return (item, name)
    
    
    def removeItem(self, item):
        self.view.scene().removeItem(item)
    
    def listItems(self):
        """Return a dictionary of name:item pairs"""
        return self.items
        
        
if __name__ == '__main__':
    app = QtGui.QApplication([])
    w = QtGui.QMainWindow()
    c = Canvas()
    w.setCentralWidget(c)
    w.show()
    w.resize(600, 600)
    
    
    import numpy as np
    
    img1 = np.random.normal(size=(200, 200))
    img2 = np.random.normal(size=(200, 200))
    def fn(x, y):
        return (x**2 + y**2)**0.5
    img1 += np.fromfunction(fn, (200, 200))
    img2 += np.fromfunction(lambda x,y: fn(x-100, y-100), (200, 200))
    
    img3 = np.random.normal(size=(200, 200, 200))
    
    c.addImage(img1, scale=[0.01, 0.01], name="Image 1")
    c.addImage(img2, scale=[0.01, 0.01], pos=[-1, -1], name="Image 2")
    
    