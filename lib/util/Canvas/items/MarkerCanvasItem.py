# -*- coding: utf-8 -*-
from CanvasItem import CanvasItem


class MarkerCanvasItem(CanvasItem):
    def __init__(self, **opts):
        item = QtGui.QGraphicsEllipseItem(-0.5, -0.5, 1., 1.)
        item.setPen(pg.mkPen((255,255,255)))
        item.setBrush(pg.mkBrush((0,100,255)))
        CanvasItem.__init__(self, item, **opts)
        
