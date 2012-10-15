"""
experimental approaches to achieving better performance for scatter plots

"""
# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)


from pyqtgraph.graphicsItems.ScatterPlotItem import makeSymbolPixmap
import numpy as np
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg

class ScatterPlot(pg.GraphicsObject):
    def __init__(self, x, y, pen=None, brush=None):
        pg.GraphicsObject.__init__(self)
        #self.setFlag(self.ItemIgnoresTransformations)
        self.x = x
        self.y = y
        self.spotImg = makeSymbolPixmap(10, pen, brush, 'o')
        #self.imgData = None
        
    def boundingRect(self):
        return QtCore.QRectF(x.min(), y.min(), x.max()-x.min(), y.max()-y.min())
        
    def paint(self, p, *args):
        #tr = pg.transformToArray(self.deviceTransform())[:2]
        tr = self.deviceTransform()
        pts = np.empty((2,len(self.x)))
        pts[0] = self.x
        pts[1] = self.y
        #pts[:,2] = 1.0
        #print tr.shape, pts.shape
        
        #pts = np.dot(tr, pts)
        pts = pg.transformCoordinates(tr, pts)
        frags = []
        for i in range(len(self.x)):
            pos = QtCore.QPointF(pts[0,i], pts[1,i])
            frags.append(QtGui.QPainter.PixmapFragment.create(pos, QtCore.QRectF(self.spotImg.rect())))
            
        p.setPen(pg.mkPen('r'))
        p.drawRect(self.boundingRect())
        p.resetTransform()
        p.drawPixmapFragments(frags, self.spotImg)
        
    #def updatePixmap(self):
        

plt = pg.plot()
plt.showGrid(x=True, y=True)
x = np.random.normal(size=100)
y = np.random.normal(size=100)
x[0] = 0
y[0] = 0

sp = ScatterPlot(x, y, pg.mkPen('w'), pg.mkBrush('b'))
plt.addItem(sp)
        
## Start Qt event loop unless running in interactive mode or using pyside.
import sys
if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    QtGui.QApplication.instance().exec_()
