from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph.multiprocess as mp
import pyqtgraph as pg
import numpy as np
import ctypes, os

__all__ = ['RemoteGraphicsView']

class RemoteGraphicsView(QtGui.QWidget):
    """
    Replacement for GraphicsView that does all scene management and rendering on a remote process,
    while displaying on the local widget.
    
    GraphicsItems must be created by proxy to the remote process.
    
    """
    def __init__(self, parent=None, *args, **kwds):
        self._img = None
        self._imgReq = None
        QtGui.QWidget.__init__(self)
        self._proc = mp.QtProcess()
        self.pg = self._proc._import('pyqtgraph')
        rpgRemote = self._proc._import('pyqtgraph.widgets.RemoteGraphicsView')
        self._view = rpgRemote.Renderer(*args, **kwds)
        self._view._setProxyOptions(deferGetattr=True)
        self._view.sceneRendered.connect(mp.proxy(self.remoteSceneChanged, callSync='off'))
        
        for method in ['scene', 'setCentralItem']:
            setattr(self, method, getattr(self._view, method))
        
    def resizeEvent(self, ev):
        ret = QtGui.QWidget.resizeEvent(self, ev)
        self._view.resize(self.size(), _callSync='off')
        return ret
        
    def remoteSceneChanged(self, data):
        print "scene changed"
        self._img = pg.makeQImage(data, alpha=True)
        print "made image"
        self.update()
        
    def paintEvent(self, ev):
        print "paint start"
        if self._img is None:
            return
        p = QtGui.QPainter(self)
        p.drawImage(self.rect(), self._img, self.rect())
        p.end()
        print "paint done"
        
    def mousePressEvent(self, ev):
        self._view.mousePressEvent(ev.type(), ev.pos(), ev.globalPos(), ev.button(), int(ev.buttons()), int(ev.modifiers()))
        ev.accept()
        return QtGui.QWidget.mousePressEvent(self, ev)

    def mouseReleaseEvent(self, ev):
        self._view.mouseReleaseEvent(ev.type(), ev.pos(), ev.globalPos(), ev.button(), int(ev.buttons()), int(ev.modifiers()))
        ev.accept()
        return QtGui.QWidget.mouseReleaseEvent(self, ev)

    def mouseMoveEvent(self, ev):
        self._view.mouseMoveEvent(ev.type(), ev.pos(), ev.globalPos(), ev.button(), int(ev.buttons()), int(ev.modifiers()))
        ev.accept()
        return QtGui.QWidget.mouseMoveEvent(self, ev)
        
class Renderer(pg.GraphicsView):
    
    sceneRendered = QtCore.Signal(object)
    
    def __init__(self, *args, **kwds):
        pg.GraphicsView.__init__(self, *args, **kwds)
        self.scene().changed.connect(self.update)
        self.img = None
        self.renderTimer = QtCore.QTimer()
        self.renderTimer.timeout.connect(self.renderView)
        self.renderTimer.start(16)
        
    def update(self):
        self.img = None
        return pg.GraphicsView.update(self)
        
    def resize(self, size):
        oldSize = self.size()
        pg.GraphicsView.resize(self, size)
        self.resizeEvent(QtGui.QResizeEvent(size, oldSize))
        self.update()
        
    def renderView(self):
        if self.img is None:
            print "render start.."
            self.img = QtGui.QImage(self.width(), self.height(), QtGui.QImage.Format_ARGB32)
            self.img.fill(0xffffffff)
            p = QtGui.QPainter(self.img)
            self.render(p, self.viewRect(), self.rect())
            p.end()
            self.data = np.fromstring(ctypes.string_at(int(self.img.bits()), self.img.byteCount()), dtype=np.ubyte).reshape(self.height(), self.width(),4).transpose(1,0,2)
            #self.data = ctypes.string_at(int(self.img.bits()), self.img.byteCount())
            print "render done"
            self.sceneRendered.emit(self.data)
            print "emit done"

    def mousePressEvent(self, typ, pos, gpos, btn, btns, mods):
        print btn, btns
        typ = QtCore.QEvent.Type(typ)
        btns = QtCore.Qt.MouseButtons(btns)
        mods = QtCore.Qt.KeyboardModifiers(mods)
        return pg.GraphicsView.mousePressEvent(self, QtGui.QMouseEvent(typ, pos, gpos, btn, btns, mods))

    def mouseMoveEvent(self, typ, pos, gpos, btn, btns, mods):
        print "move"
        typ = QtCore.QEvent.Type(typ)
        btns = QtCore.Qt.MouseButtons(btns)
        mods = QtCore.Qt.KeyboardModifiers(mods)
        return pg.GraphicsView.mouseMoveEvent(self, QtGui.QMouseEvent(typ, pos, gpos, btn, btns, mods))

    def mouseReleaseEvent(self, typ, pos, gpos, btn, btns, mods):
        typ = QtCore.QEvent.Type(typ)
        btns = QtCore.Qt.MouseButtons(btns)
        mods = QtCore.Qt.KeyboardModifiers(mods)
        return pg.GraphicsView.mouseReleaseEvent(self, QtGui.QMouseEvent(typ, pos, gpos, btn, btns, mods))

