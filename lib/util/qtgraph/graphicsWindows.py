# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
#from GraphicsView import *
#from graphicsWindow import *
#from graphicsItems import *
#from scipy import *
#import time, types
#from lib.util.MetaArray import *
#from PlotWidgetTemplate import Ui_Form as PlotWidgetTemplate
from PlotWidget import *
from ImageView import *

class PlotWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        QtGui.QMainWindow.__init__(self)
        self.cw = PlotWidget()
        self.setCentralWidget(self.cw)
        for m in ['plot', 'autoRange']:
            setattr(self, m, getattr(self.cw, m))

class ImageWindow(QtGui.QMainWindow):
    def __init__(self, title=None):
        QtGui.QMainWindow.__init__(self)
        self.cw = ImageView()
        self.setCentralWidget(self.cw)
        for m in ['setImage', 'autoRange']:
            setattr(self, m, getattr(self.cw, m))



#class PlotWindow(QtGui.QMainWindow):
    #def __init__(self, data, parent=None, title=None):
        #QtGui.QWidget.__init__(self, parent)
        #self.ui = Ui_MainWindow()
        #self.ui.setupUi(self)
        #if title is not None:
            #self.setWindowTitle(title)
        #self.scene = QtGui.QGraphicsScene(self)
        ##self.traces = []
        ##self.drawData(data)
        #self.plots = []
        #self.addPlot(data)
        
        #g = Grid(view=self.ui.graphicsView)
        #g.setZValue(-1)
        #self.scene.addItem(g)
        
        #self.ui.graphicsView.setScene(self.scene)
        ##self.ui.graphicsView.scale(1.0, -1.0)
        #self.ui.ImageLUTDock.hide()
        #self.ui.timeControlDock.hide()
        #self.show()
        #self.autoRange()
        #self.statusLabel = QtGui.QLabel()
        #self.statusBar().addPermanentWidget(self.statusLabel)
        #QtCore.QObject.connect(self.ui.graphicsView, QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.setMouse)
    
    #def addPlot(self, data):
        #numPl = 0
        #for p in self.plots:
            #numPl += p.numColumns()
        #self.plots.append(Plot(data, color=numPl))
        #self.plots[-1].setZValue(1)
        #self.scene.addItem(self.plots[-1])
    
    #def autoRange(self):
        ##self.ui.graphicsView.setRange(QtCore.QRectF(0, self.data.min(), self.data.shape[1], self.data.max()-self.data.min()))
        #self.ui.graphicsView.setRange(self.plots[0].boundingRect())
    
    #def color(self, ind):
        #x = (ind * 280) % (256*3)
        #r = clip(255-abs(x), 0, 255) + clip(255-abs(x-768), 0, 255)
        #g = clip(255-abs(x-256), 0, 255)
        #b = clip(255-abs(x-512), 0, 255)
        #return (r, g, b)
    
    #def drawData(self, data):
        #self.data = atleast_2d(data)
        ##data = atleast_2d(data)
        #for i in range(0, self.data.shape[0]):
            #c = self.color(len(self.traces))
            #self.traces.append([])
            #for j in range(1, self.data.shape[1]):
                #l = self.scene.addLine(j-1, self.data[i, j-1], j, self.data[i, j], QtGui.QPen(QtGui.QColor(*c)))
                #self.traces[-1].append(l)
    
    #def setMouse(self, pos):
        #self.statusLabel.setText("X:%0.2f Y:%0.2f" % (pos.x(), pos.y()))
        
    #def getFreehandLine(self, msg="Draw a curve on the image."):
        ## Set statusbar text
        #self.statusBar().showMessage(msg)
        
        ## Set crosshair
        ##dragMode = self.ui.graphicsView.dragMode()
        ##self.ui.graphicsView.setDragMode(QtGui.QGraphicsView.NoDrag)
        
        ## Wait for click
        #self.ui.graphicsView.clearMouse()
        #while self.ui.graphicsView.lastButtonReleased != QtCore.Qt.LeftButton:
            #QtGui.qApp.sendPostedEvents()
            #QtGui.qApp.processEvents()
            #time.sleep(0.01)
        #self.statusBar().clearMessage()
        #fl = vstack(self.ui.graphicsView.mouseTrail)
        #return fl
    
    #def getClick(self, msg="Click a point on the image."):
        #fl = self.getFreehandLine(msg=msg)
        #return fl[-1]

    #def getFreehandLine(self, msg="Draw a curve on the image."):
        #return self.ui.graphicsView.getFreehandLine(msg)

    #def getClick(self, msg="Click a point on the image."):
        #return self.ui.graphicsView.getClick(msg)


#class ImageWindow(QtGui.QMainWindow):
    #def __init__(self, image, parent=None, title=None, copy=True):
        #QtGui.QWidget.__init__(self)
        #self.ui = Ui_MainWindow()
        #self.ui.setupUi(self)
        #if title is not None:
            #self.setWindowTitle(title)
        #self.scene = QtGui.QGraphicsScene(self)
        #self.imageItem = ImageItem()
        #self.scene.addItem(self.imageItem)
        #self.ui.graphicsView.setScene(self.scene)
        #self.ui.graphicsView.setAspectLocked(True)
        #self.ui.graphicsView.invertY()
        #self.xyLabel = QtGui.QLabel()
        #self.tLabel = QtGui.QLabel()
        #self.vLabel = QtGui.QLabel()
        #font = self.xyLabel.font()
        #font.setPointSize(8)
        #self.xyLabel.setFont(font)
        #self.tLabel.setFont(font)
        #self.vLabel.setFont(font)
        #self.statusBar().addPermanentWidget(self.xyLabel)
        #self.statusBar().addPermanentWidget(self.tLabel)
        #self.statusBar().addPermanentWidget(self.vLabel)
        #self.axes = None
        ##self.ui.timeControlDock.hide()
        #self.show()
        #self.updateImage(image, autoRange=True, copy=copy)
        
        #g = Grid(self.ui.graphicsView)
        #g.setZValue(-1)
        #self.scene.addItem(g)
        
        #QtCore.QObject.connect(self.ui.blackLevel, QtCore.SIGNAL('valueChanged(int)'), self.updateLevels)
        #QtCore.QObject.connect(self.ui.whiteLevel, QtCore.SIGNAL('valueChanged(int)'), self.updateLevels)
        #QtCore.QObject.connect(self.ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        #QtCore.QObject.connect(self.ui.graphicsView, QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.setMouse)
        #self.ui.whiteLevel.setMaximum((2**16)-1)
        #self.ui.blackLevel.setMaximum((2**16)-1)
        #self.ui.whiteLevel.setValue((2**16)-1)
        #self.ui.blackLevel.setValue(0)
        #self.ui.whiteLevel.setMinimum(0)
        #self.ui.blackLevel.setMinimum(0)
        #self.plotWindow = None
    
    #def updateLevels(self):
        #self.imageItem.setLevels(white=self.whiteLevel(), black=self.blackLevel())
    
    #def updateImage(self, image=None, axes=None, autoRange=False, copy=True):
        #if type(image) == ndarray:
            #if copy:
                #self.data = image.copy()
            #else:
                #self.data = image
        #elif type(image) == types.IntType:
            #image = None
        
        #if self.data.ndim > 4 or self.data.ndim < 2:
            #raise Exception("Can only handle 2-4 axes currently :(")
            
        ### Try to automatically determine which axes are which
        #if axes is not None:
            #self.axes = axes
        #if self.axes is None or (image is not None and axes is None):
            #if self.data.ndim == 2:
                #self.axes = ['x', 'y']
            #elif self.data.ndim == 3:
                #if self.data.shape[2] < 5:
                    #self.axes = ['x', 'y', 'c']
                #else:
                    #self.axes = ['t', 'x', 'y']
            #elif self.data.ndim == 4:
                #self.axes = ['t', 'x', 'y', 'c']
        #axes = self.axes[:]
        ### If there is a time axis, take the current timepoint
        #if 't' in axes:
            #tax = axes.index('t')
            #self.ui.timeSlider.setMinimum(0)
            #self.ui.timeSlider.setMaximum(self.data.shape[tax]-1)
            #ind = [slice(None)]*self.data.ndim
            #ind[tax] = self.ui.timeSlider.value()
            #self.tLabel.setText("T: %d" % self.ui.timeSlider.value())
            #self.image = self.data[tuple(ind)]
            #axes.remove('t')
        #else:
            #self.ui.timeControlDock.hide()
            #self.image = self.data
        
        #axh = {}
        #for i in range(0, len(axes)):
            #axh[axes[i]] = i
            
        #if autoRange:
            #self.autoRange()
            
        #self.imageItem.updateImage(self.image, autoRange=False, copy=False)
    
    #def setMouse(self, qpt):
        #x = qpt.x()
        #y = qpt.y()
        #if y >= 0 and x >= 0 and y < self.image.shape[1] and x < self.image.shape[0]:
            #z = self.image[int(x), int(y)]
            
            #if 'shape' in dir(z) and len(z.shape) > 0:
                #z = "Z:(%s, %s, %s)" % (str(z[0]), str(z[1]), str(z[2]))
            #else:
                #z = "Z:%s" % str(z)
            
            #t = ''
            #if self.ui.timeControlDock.isVisible():
                #t = "T: %d " % self.ui.timeSlider.value()
            
            #self.xyLabel.setText("X:%0.2f Y:%0.2f" % (x, y))
            #self.vLabel.setText(z)
            
    #def autoRange(self):
        #self.levelMax = float(self.data.max())
        #self.levelMin = float(self.data.min())
        
        #self.ui.whiteLevel.setValue(self.ui.whiteLevel.maximum())
        #self.ui.blackLevel.setValue(0)
        #self.imageItem.setLevels(white=self.whiteLevel(), black=self.blackLevel())
        
        #self.ui.graphicsView.setRange(QtCore.QRectF(0, 0, self.image.shape[0], self.image.shape[1]), padding=0., lockAspect=True)
        
    #def whiteLevel(self):
        #return self.levelMin + (self.levelMax-self.levelMin) * self.ui.whiteLevel.value() / self.ui.whiteLevel.maximum() 
    
    #def blackLevel(self):
        #return self.levelMin + ((self.levelMax-self.levelMin) / self.ui.blackLevel.maximum()) * self.ui.blackLevel.value()
        
        
    
    #def drawPlot(self, trail):
        #p0 = trail[0]
        #p1 = trail[-1]
        #tr = self.data[:, p0[0]:p1[0], p0[1]:p1[1]]
        #tr = tr.mean(axis=2).mean(axis=1)
        #if self.plotWindow is None or not self.plotWindow.isVisible():
            #self.plotWindow = PlotWindow(tr, title=self.windowTitle() + " ROI traces")
        #else:
            #self.plotWindow.addPlot(tr)
    
    #def trace(self, img=None):
        #if img is None:
            #img = self
        #QtCore.QObject.connect(self.ui.graphicsView, QtCore.SIGNAL('mouseReleased(PyQt_PyObject)'), img.drawPlot)

    #def getFreehandLine(self, msg="Draw a curve on the image."):
        #self.statusBar().showMessage(msg)
        #l = self.ui.graphicsView.getFreehandLine()
        #self.statusBar().clearMessage()
        #return l

    #def getClick(self, msg="Click a point on the image."):
        #self.statusBar().showMessage(msg)
        #pt = self.ui.graphicsView.getClick()
        #self.statusBar().clearMessage()
        #return pt






#class PlotWidget(QtGui.QWidget):
    #def __init__(self, color=0, parent=None):
        #QtGui.QWidget.__init__(self, parent)
        #self.ui = PlotWidgetTemplate()
        #self.ui.setupUi(self)
        #self.cwLayout = QtGui.QGridLayout()
        #self.ui.centralWidget.setLayout(self.cwLayout)
        #self.view = GraphicsView()
        #self.cwLayout.addWidget(self.view)
        #self.scene = QtGui.QGraphicsScene()
        #self.grid = Grid(self.view)
        #self.scene.addItem(self.grid)
        #self.view.setScene(self.scene)
        #self.plots = []
        #self.nextColor = color
        #self.autoScale = [False, True]
        #QtCore.QObject.connect(self.ui.btnClose, QtCore.SIGNAL('clicked()'), self.closeClicked)
    
    #def addPlot(self, plot):
        #plot.connect(QtCore.SIGNAL('plotChanged'), self.plotChangedEvent)
        #self.plots.append(plot)
        #self.nextColor += self.plots[-1].numColumns()
        #self.plots[-1].setZValue(1)
        #self.scene.addItem(self.plots[-1])
        ##self.plotChangedEvent(None)
        #return len(self.plots) - 1
    
    #def createPlot(self, data, xVals=None, color=None):
        #self.addPlot(Plot(data, xVals, color=color))
        
    #def plotChangedEvent(self, p):
        #if self.ui.btnHorizScale.isChecked():
            #if len(self.plots) > 0:
                #b = self.plotBounds()
                #if self.autoScale[0]:
                    #self.view.setXRange(b, padding)
                #if self.autoScale[1]:
                    #self.view.setYRange(b)
            
    #def autoRange(self, padding=0.5):
        #b = self.plotBounds(padding=0)
        #self.view.setRange(b, padding=padding)
        
    #def plotBounds(self, padding=0.05):
        #b = self.plots[0].boundingRect()
        #for i in range(1, len(self.plots)):
            #b = b.united(self.plots[i].boundingRect())
        #b = b.adjusted(-b.width()*padding, -b.height()*padding, b.width()*padding, b.height()*padding)
        #return b
        
    #def closeClicked(self):
        #self.setVisible(False)
        #self.emit(QtCore.SIGNAL('closed'))
