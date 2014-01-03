# -*- coding: utf-8 -*-
from acq4.pyqtgraph.Qt import QtCore, QtGui, QtSvg
from CanvasItem import CanvasItem

class SvgCanvasItem(CanvasItem):
    
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
        
        
    