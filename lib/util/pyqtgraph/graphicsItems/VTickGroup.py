from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph.functions as fn
import weakref


class VTickGroup(QtGui.QGraphicsPathItem):
    """
    Draws a set of tick marks which always occupy the same vertical range of the view,
    but have x coordinates relative to the data within the view.
    
    """
    def __init__(self, xvals=None, yrange=None, pen=None, relative=False, view=None):
        QtGui.QGraphicsPathItem.__init__(self)
        if yrange is None:
            yrange = [0, 1]
        if xvals is None:
            xvals = []
        if pen is None:
            pen = (200, 200, 200)
        self.ticks = []
        self.xvals = []
        if view is None:
            self.view = None
        else:
            self.view = weakref.ref(view)
        self.yrange = [0,1]
        self.setPen(pen)
        self.setYRange(yrange, relative)
        self.setXVals(xvals)
        self.valid = False
        
    def setPen(self, pen):
        pen = fn.mkPen(pen)
        QtGui.QGraphicsPathItem.setPen(self, pen)

    def setXVals(self, vals):
        self.xvals = vals
        self.rebuildTicks()
        self.valid = False
        
    def setYRange(self, vals, relative=False):
        self.yrange = vals
        self.relative = relative
        if self.view is not None:
            if relative:
                #QtCore.QObject.connect(self.view, QtCore.SIGNAL('viewChanged'), self.rebuildTicks)
                #QtCore.QObject.connect(self.view(), QtCore.SIGNAL('viewChanged'), self.rescale)
                self.view().sigRangeChanged.connect(self.rescale)
            else:
                try:
                    #QtCore.QObject.disconnect(self.view, QtCore.SIGNAL('viewChanged'), self.rebuildTicks)
                    #QtCore.QObject.disconnect(self.view(), QtCore.SIGNAL('viewChanged'), self.rescale)
                    self.view().sigRangeChanged.disconnect(self.rescale)
                except:
                    pass
        self.rebuildTicks()
        self.valid = False
            
    def rescale(self):
        #print "RESCALE:"
        self.resetTransform()
        #height = self.view.size().height()
        #p1 = self.mapFromScene(self.view.mapToScene(QtCore.QPoint(0, height * (1.0-self.yrange[0]))))
        #p2 = self.mapFromScene(self.view.mapToScene(QtCore.QPoint(0, height * (1.0-self.yrange[1]))))
        #yr = [p1.y(), p2.y()]
        vb = self.view().viewRect()
        p1 = vb.bottom() - vb.height() * self.yrange[0]
        p2 = vb.bottom() - vb.height() * self.yrange[1]
        yr = [p1, p2]
        
        #print "  ", vb, yr
        self.translate(0.0, yr[0])
        self.scale(1.0, (yr[1]-yr[0]))
        #print "  ", self.mapRectToScene(self.boundingRect())
        self.boundingRect()
        self.update()
            
    def boundingRect(self):
        #print "--request bounds:"
        b = QtGui.QGraphicsPathItem.boundingRect(self)
        #print "  ", self.mapRectToScene(b)
        return b
            
    def yRange(self):
        #if self.relative:
            #height = self.view.size().height()
            #p1 = self.mapFromScene(self.view.mapToScene(QtCore.QPoint(0, height * (1.0-self.yrange[0]))))
            #p2 = self.mapFromScene(self.view.mapToScene(QtCore.QPoint(0, height * (1.0-self.yrange[1]))))
            #return [p1.y(), p2.y()]
        #else:
            #return self.yrange
            
        return self.yrange
            
    def rebuildTicks(self):
        self.path = QtGui.QPainterPath()
        yrange = self.yRange()
        #print "rebuild ticks:", yrange
        for x in self.xvals:
            #path.moveTo(x, yrange[0])
            #path.lineTo(x, yrange[1])
            self.path.moveTo(x, 0.)
            self.path.lineTo(x, 1.)
        self.setPath(self.path)
        self.valid = True
        self.rescale()
        #print "  done..", self.boundingRect()
        
    def paint(self, *args):
        if not self.valid:
            self.rebuildTicks()
        #print "Paint", self.boundingRect()
        QtGui.QGraphicsPathItem.paint(self, *args)
