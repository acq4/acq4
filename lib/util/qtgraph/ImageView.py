# -*- coding: utf-8 -*-
from ImageViewTemplate import *
from graphicsItems import *
from PyQt4 import QtCore, QtGui

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
        QtCore.QObject.connect(self.ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), self.timeChanged)
        QtCore.QObject.connect(self.ui.whiteSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        QtCore.QObject.connect(self.ui.blackSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        
    def setImage(self, img):
        self.image = img
        self.ui.timeSlider.setValue(0)
        #self.ui.timeSlider.setMaximum(img.shape[0]-1)
        self.updateImage()
        self.autoRange()
        
    def timeChanged(self):
        ind = self.timeIndex()
        if ind != self.currentIndex:
            self.currentIndex = ind
            self.updateImage()

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
        v = self.ui.timeSlider.value()
        vmax = self.ui.timeSlider.maximum()
        f = float(v) / vmax
        xv = self.image.xvals('Time') 
        if xv is None:
            ind = int(f * self.image.shape[0])
        else:
            if len(xv) < 2:
                return 0
            totTime = xv[-1] + (xv[-1]-xv[-2])
            t = f * totTime
            inds = argwhere(xv < t)
            if len(inds) < 1:
                return 0
            ind = inds[-1,0]
        #print ind
        return ind
            
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
        