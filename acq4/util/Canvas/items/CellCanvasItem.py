# -*- coding: utf-8 -*-
from CanvasItem import CanvasItem
from PyQt4 import QtCore, QtGui
import acq4.pyqtgraph as pg
import acq4.Manager
from .itemtypes import registerItemType


class CellCanvasItem(CanvasItem):
    """
    Canvas item used for marking the location of cells.
    
    """
    _typeName = "Cell"
    
    def __init__(self, **opts):
        if 'scale' not in opts:
            opts['scale'] = [20e-6, 20e-6]
        item = QtGui.QGraphicsEllipseItem(-0.5, -0.5, 1., 1.)
        item.setPen(pg.mkPen((255,255,255)))
        item.setBrush(pg.mkBrush((0,100,255)))
        opts.setdefault('scalable', False)
        opts.setdefault('rotatable', False)
        CanvasItem.__init__(self, item, **opts)
        self.selectBox.addTranslateHandle([0.5,0.5])
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile():
            return 0
        try:
            model = acq4.Manager.getManager().dataModel
            if model.dirType(fh) == 'Cell':
                return 100
            return 0
        except AttributeError:
            return 0
        
registerItemType(CellCanvasItem)


    