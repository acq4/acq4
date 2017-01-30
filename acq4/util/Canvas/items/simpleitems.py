# -*- coding: utf-8 -*-
from acq4.pyqtgraph.Qt import QtCore, QtGui, QtSvg
import acq4.pyqtgraph as pg
from CanvasItem import CanvasItem
from .itemtypes import registerItemType



class GridCanvasItem(CanvasItem):
    _typeName = "Grid"
    
    def __init__(self, **kwds):
        item = pg.GridItem()
        CanvasItem.__init__(self, item, **kwds)

registerItemType(GridCanvasItem)


class RulerCanvasItem(CanvasItem):
    _typeName = "Ruler"
    
    def __init__(self, points=((0, 0), (1, 1)), **kwds):
        item = pg.graphicsItems.ROI.RulerROI(points)
        CanvasItem.__init__(self, item, **kwds)

registerItemType(RulerCanvasItem)


class SvgCanvasItem(CanvasItem):
    _typeName = "SVG"
    
    def __init__(self, handle, **opts):
        opts['handle'] = handle
        item = QtSvg.QGraphicsSvgItem(handle.name())
        CanvasItem.__init__(self, item, **opts)
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile() and fh.ext() == '.svg':
            return 100
        else:
            return 0
        
registerItemType(SvgCanvasItem)
        
    