# -*- coding: utf-8 -*-
from CanvasItem import CanvasItem
import pyqtgraph as pg
class GroupCanvasItem(CanvasItem):
    """
    Canvas item used for grouping others
    """
    
    def __init__(self, **opts):
        defOpts = {'movable': False, 'scalable': False}
        defOpts.update(opts)
        item = pg.ItemGroup()
        CanvasItem.__init__(self, item, **defOpts)
    
    @classmethod
    def checkFile(cls, fh):
        return 0
    