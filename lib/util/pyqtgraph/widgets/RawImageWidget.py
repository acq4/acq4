from pyqtgraph.Qt import QtCore, QtGui, QtOpenGL

import pyqtgraph.functions as fn
import numpy as np

class RawImageWidget(QtGui.QWidget):
    """
    Widget optimized for very fast video display. 
    Generally using an ImageItem inside GraphicsView is fast enough,
    but if you need even more performance, this widget is about as fast as it gets.

    The tradeoff is that this widget will _only_ display the unscaled image
    and nothing else. 
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent=None)
        self.image = None
    
    def setImage(self, img):
        """Scale may be any integer > 1, but this will slow things down a little."""
        self.image = fn.makeQImage(img)
        self.update()

    def paintEvent(self, ev):
        if self.image is None:
            return
        #if self.pixmap is None:
            #self.pixmap = QtGui.QPixmap.fromImage(self.image)
        p = QtGui.QPainter(self)
        p.drawImage(QtCore.QPointF(), self.image)
        #p.drawPixmap(self.rect(), self.pixmap)
        p.end()


class RawImageGLWidget(QtOpenGL.QGLWidget):
    """
    Similar to RawImageWidget, but uses a GL widget to do all drawing. 
    Generally this will be about as fast as using GraphicsView + ImageItem,
    but performance may vary on some platforms.
    """
    def __init__(self, parent=None):
        QtOpenGL.QGLWidget.__init__(self, parent=None)
        self.image = None
    
    def setImage(self, img):
        self.image = fn.makeQImage(img)
        self.update()

    def paintEvent(self, ev):
        if self.image is None:
            return
        p = QtGui.QPainter(self)
        p.drawImage(self.rect(), self.image)
        p.end()


