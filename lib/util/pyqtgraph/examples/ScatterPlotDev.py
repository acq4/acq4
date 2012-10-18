"""
experimental approaches to achieving better performance for scatter plots

"""
# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)


from pyqtgraph.graphicsItems.ScatterPlotItem import makeSymbolPixmap, drawSymbol
import numpy as np
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg

class ScatterPlot(pg.GraphicsObject):
    def __init__(self, x, y, pen=None, brush=None, pxMode=True):
        pg.GraphicsObject.__init__(self)
        #self.setFlag(self.ItemIgnoresTransformations)
        self.x = x
        self.y = y
        self.spotImg = makeSymbolPixmap(10, pen, brush, 'o')
        self.picture = None
        self.pxMode = pxMode
        self.pen = pen
        self.brush = brush
        #self.imgData = None
        
    def boundingRect(self):
        return QtCore.QRectF(x.min(), y.min(), x.max()-x.min(), y.max()-y.min())
        
    def setData(self, x, y):
        self.x = x
        self.y = y
        self.picture = None
        self.update()
        
    def paint(self, p, *args):
        if self.pxMode:
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
                
            #p.setPen(pg.mkPen('r'))
            #p.drawRect(self.boundingRect())
            p.resetTransform()
            p.drawPixmapFragments(frags, self.spotImg)
        else:
            if self.picture is None:
                self.picture = QtGui.QPicture()
                p2 = QtGui.QPainter(self.picture)
                for i in range(len(self.x)):
                    p2.resetTransform()
                    p2.translate(self.x[i], self.y[i])
                    drawSymbol(p2, 'o', 10, self.pen, self.brush)
                p2.end()
                
            self.picture.play(p)
    #def updatePixmap(self):
        

plt = pg.plot()
#plt.showGrid(x=True, y=True)
x = np.random.normal(size=(1000, 50))*1000
y = np.random.normal(size=(1000, 50))*1000
x[0] = 0
y[0] = 0

sp = ScatterPlot(x[:,0], y[:,0], pg.mkPen('w'), pg.mkBrush('b'), pxMode=False)
plt.addItem(sp)


plt2 = pg.plot()
sp2 = plt2.plot(x[:,0], y[:,0], pen=None, symbolPen='w', symbolBrush='b', pxMode=False)

i = 0
def update():
    global i
    sp2.setData(x[:,i], y[:,i])
    plt2.repaint()
    i = (i+1) % 50
    
t = QtCore.QTimer()
t.timeout.connect(update)
#t.start(0)

## Start Qt event loop unless running in interactive mode or using pyside.
import sys
if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
    QtGui.QApplication.instance().exec_()
