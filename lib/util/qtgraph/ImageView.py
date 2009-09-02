# -*- coding: utf-8 -*-
from ImageViewTemplate import *
from graphicsItems import *
from widgets import ROI
from PyQt4 import QtCore, QtGui
from PyQt4 import Qwt5 as Qwt

class PlotROI(ROI):
    def __init__(self, size):
        ROI.__init__(self, pos=[0,0], size=size, scaleSnap=True, translateSnap=True)
        self.addScaleHandle([1, 1], [0, 0])


class ImageView(QtGui.QWidget):
    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)
        self.levelMax = 4096
        self.levelMin = 0
        self.image = None
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.scene = QtGui.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setAspectLocked(True)
        self.ui.graphicsView.invertY()
        self.imageItem = ImageItem()
        self.scene.addItem(self.imageItem)
        self.currentIndex = 0

        self.roi = PlotROI(10)
        self.roi.setZValue(20)
        self.scene.addItem(self.roi)
        self.roi.hide()
        self.ui.roiPlot.hide()
        self.roiCurve = self.ui.roiPlot.plot()
        self.roiTimeLine = Qwt.QwtPlotMarker()
        self.roiTimeLine.setLinePen(QtGui.QPen(QtGui.QColor(255, 255, 0)))
        self.roiTimeLine.setLineStyle(Qwt.QwtPlotMarker.VLine)
        self.roiTimeLine.setXValue(0)
        self.roiTimeLine.attach(self.ui.roiPlot)


        QtCore.QObject.connect(self.ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), self.timeChanged)
        QtCore.QObject.connect(self.ui.whiteSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        QtCore.QObject.connect(self.ui.blackSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        QtCore.QObject.connect(self.ui.roiBtn, QtCore.SIGNAL('clicked()'), self.roiClicked)
        #QtCore.QObject.connect(self.roi, QtCore.SIGNAL('regionChanged'), self.roiChanged)
        self.roi.connect(QtCore.SIGNAL('regionChanged'), self.roiChanged)


    def roiClicked(self):
        if self.ui.roiBtn.isChecked():
            self.roi.show()
            self.ui.roiPlot.show()
            self.roiChanged()
        else:
            self.roi.hide()
            self.ui.roiPlot.hide()

    def roiChanged(self):
        if self.image is not None:
            data = self.roi.getArrayRegion(self.image.view(ndarray), self.imageItem, (1, 2))
            if data is not None:
                data = data.mean(axis=1).mean(axis=1)
                self.roiCurve.setData(y=data, x=self.image.xvals(0))
                self.ui.roiPlot.replot()

    def setImage(self, img):
        self.image = img
        self.ui.timeSlider.setValue(0)
        #self.ui.timeSlider.setMaximum(img.shape[0]-1)
        self.updateImage()
        self.autoRange()
        if self.ui.roiBtn.isChecked():
            self.roiChanged()
        
    def timeChanged(self):
        (ind, time) = self.timeIndex()
        if ind != self.currentIndex:
            self.currentIndex = ind
            self.updateImage()
        self.roiTimeLine.setXValue(time)
        self.ui.roiPlot.replot()
        self.emit(QtCore.SIGNAL('timeChanged'), ind, time)

    def updateImage(self):
        if self.image is None:
            return
        if self.image.ndim == 3:
            self.ui.timeSlider.show()
            self.imageItem.updateImage(self.image[self.currentIndex], white=self.whiteLevel(), black=self.blackLevel())
        elif self.image.ndim == 2:
            self.ui.timeSlider.hide()
            self.imageItem.updateImage(self.image, white=self.whiteLevel(), black=self.blackLevel())
            
    def timeIndex(self):
        if self.image is None:
            return (0,0)
        v = self.ui.timeSlider.value()
        vmax = self.ui.timeSlider.maximum()
        f = float(v) / vmax
        t = 0.0
        xv = self.image.xvals('Time') 
        if xv is None:
            ind = int(f * self.image.shape[0])
        else:
            if len(xv) < 2:
                return (0,0)
            totTime = xv[-1] + (xv[-1]-xv[-2])
            t = f * totTime
            inds = argwhere(xv < t)
            if len(inds) < 1:
                return (0,t)
            ind = inds[-1,0]
        #print ind
        return ind, t
            
    def autoRange(self):
        self.levelMax = float(self.image.max())
        self.levelMin = float(self.image.min())
        
        self.ui.whiteSlider.setValue(self.ui.whiteSlider.maximum())
        self.ui.blackSlider.setValue(0)
        self.imageItem.setLevels(white=self.whiteLevel(), black=self.blackLevel())
        
        if self.image.ndim == 2:
            axes = (0, 1)
        elif self.image.ndim == 3:
            axes = (1, 2)
        self.ui.graphicsView.setRange(QtCore.QRectF(0, 0, self.image.shape[axes[0]], self.image.shape[axes[1]]), padding=0., lockAspect=True)        

    def whiteLevel(self):
        return self.levelMin + (self.levelMax-self.levelMin) * self.ui.whiteSlider.value() / self.ui.whiteSlider.maximum() 
    
    def blackLevel(self):
        return self.levelMin + ((self.levelMax-self.levelMin) / self.ui.blackSlider.maximum()) * self.ui.blackSlider.value()
        