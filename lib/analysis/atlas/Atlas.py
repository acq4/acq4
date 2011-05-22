# -*- coding: utf-8 -*-
from PyQt4 import QtCore
class Atlas(QtCore.QObject):
    """An Atlas is responsible for determining the position of images, cells, scan data, etc relative
    to a common coordinate system."""
    def __init__(self, canvas, state=None):
        QtCore.QObject.__init__(self)
        self.canvas = canvas
        if state is not None:
            self.restoreState(state)
    
    def getCtrlWidget(self):
        raise Exception("Must be reimplemented in subclass.")
    
    def mapToAtlas(self, obj):
        """Maps obj into atlas coordinates. Obj can be any object mappable by QMatrix4x4"""
        raise Exception("Must be reimplemented in subclass.")

    def saveState(self):
        raise Exception("Must be reimplemented in subclass.")

    def restoreState(self):
        raise Exception("Must be reimplemented in subclass.")

    def close(self):
        pass
        