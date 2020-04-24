# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import acq4.pyqtgraph as pg
from .CanvasItem import CanvasItem
from .itemtypes import registerItemType



class GridCanvasItem(CanvasItem):
    _typeName = "Grid"
    
    def __init__(self, **kwds):
        kwds.pop('viewRect', None)
        item = pg.GridItem()
        CanvasItem.__init__(self, item, **kwds)

registerItemType(GridCanvasItem)


class RulerCanvasItem(CanvasItem):
    _typeName = "Ruler"
    
    def __init__(self, points=None, **kwds):
        vr = kwds.pop('viewRect', None)
        if points is None:
            if vr is None:
                points = ((0, 0), (1, 1))
            else:
                p1 = vr.center()
                p2 = p1 + 0.2 * (vr.topRight()-p1)
                points = ((p1.x(), p1.y()), (p2.x(), p2.y()))
        item = pg.graphicsItems.ROI.RulerROI(points)
        CanvasItem.__init__(self, item, **kwds)

registerItemType(RulerCanvasItem)


class SvgCanvasItem(CanvasItem):
    _typeName = "SVG"
    
    def __init__(self, handle, **opts):
        opts['handle'] = handle
        item = Qt.QGraphicsSvgItem(handle.name())
        CanvasItem.__init__(self, item, **opts)
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile() and fh.ext() == '.svg':
            return 100
        else:
            return 0
        
registerItemType(SvgCanvasItem)
        
    