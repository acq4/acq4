# -*- coding: utf-8 -*-
from CanvasItem import CanvasItem
from PyQt4 import QtCore, QtGui
import pyqtgraph as pg
import lib.Manager

class CellCanvasItem(CanvasItem):
    """
    Canvas item used for marking the location of cells.
    
    """
    
    def __init__(self, **opts):
        if 'scale' not in opts:
            opts['scale'] = [20e-6, 20e-6]
            #opts['size'] = [20e-6, 20e-6]
            #opts['scale'] = [1., 1.]
        item = QtGui.QGraphicsEllipseItem(-0.5, -0.5, 1., 1.)
        item.setPen(pg.mkPen((255,255,255)))
        item.setBrush(pg.mkBrush((0,100,255)))
        CanvasItem.__init__(self, item, **opts)
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile():
            return 0
        try:
            model = lib.Manager.getManager().dataModel
            if model.dirType(fh) == 'Cell':
                return 100
            return 0
        except AttributeError:
            return 0
        
    