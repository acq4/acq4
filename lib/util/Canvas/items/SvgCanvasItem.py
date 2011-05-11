# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from CanvasItem import CanvasItem

class SvgCanvasItem(CanvasItem):
    
    def __init__(self, handle, **opts):
        item = QtSvg.QGraphicsSvgItem(handle.name())
        CanvasItem.__init__(self, item, **opts)
    
    @classmethod
    def checkFile(cls, fh):
        if fh.isFile() and fh.ext() == '.svg':
            return 100
        else:
            return 0
        
        
    