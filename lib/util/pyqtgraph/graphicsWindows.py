# -*- coding: utf-8 -*-
"""
graphicsWindows.py -  Convenience classes which create a new window with PlotWidget or ImageView.
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from PyQt4 import QtCore, QtGui
from PlotWidget import *
from ImageView import *
QAPP = None

def mkQApp():
    if QtGui.QApplication.instance() is None:
        global QAPP
        QAPP = QtGui.QApplication([])



class GraphicsWindow(QtGui.QMainWindow):
    def __init__(self, title=None, size=(800,600)):
        mkQApp()
        QtGui.QMainWindow.__init__(self)
        self.view = GraphicsLayoutWidget()
        self.setCentralWidget(self.view)
        self.resize(*size)
        if title is not None:
            self.setWindowTitle(title)
        self.show()
        
class GraphicsLayoutWidget(GraphicsView):
    def __init__(self, title=None, size=(800,600)):
        GraphicsView.__init__(self)
        self.items = []
        self.currentRow = 0
        self.currentCol = 0
    
    def nextRow(self):
        """Advance to next row for automatic item placement"""
        self.currentRow += 1
        self.currentCol = 0
        
    def nextCol(self, colspan=1):
        """Advance to next column, while returning the current column number 
        (generally only for internal use)"""
        self.currentCol += colspan
        return self.currentCol-colspan
        
    def addPlot(self, row=None, col=None, rowspan=1, colspan=1):
        plot = PlotItem()
        self.items.append(plot)
        if row is None:
            row = self.currentRow
        if col is None:
            col = self.nextCol(colspan)
        self.centralLayout.addItem(plot, row, col, rowspan, colspan)
        return plot


class PlotWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        mkQApp()
        QtGui.QMainWindow.__init__(self)
        self.cw = PlotWidget()
        self.setCentralWidget(self.cw)
        for m in ['plot', 'autoRange', 'addItem', 'removeItem', 'setLabel', 'clear']:
            setattr(self, m, getattr(self.cw, m))
        if title is not None:
            self.setWindowTitle(title)
        self.show()

class ImageWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        mkQApp()
        QtGui.QMainWindow.__init__(self)
        self.cw = ImageView()
        self.setCentralWidget(self.cw)
        for m in ['setImage', 'autoRange', 'addItem', 'removeItem', 'blackLevel', 'whiteLevel', 'imageItem']:
            setattr(self, m, getattr(self.cw, m))
        if title is not None:
            self.setWindowTitle(title)
        self.show()
