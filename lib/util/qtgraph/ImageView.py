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
        QtCore.QObject.connect(self.ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        QtCore.QObject.connect(self.ui.whiteSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        QtCore.QObject.connect(self.ui.blackSlider, QtCore.SIGNAL('valueChanged(int)'), self.updateImage)
        
    def setImage(self, img):
        self.image = img
        self.ui.timeSlider.setValue(0)
        self.ui.timeSlider.setMaximum(img.shape[0]-1)
        self.updateImage()
        self.autoRange()
        
    def updateImage(self):
        if self.image is None:
            return
        self.imageItem.updateImage(self.image[self.ui.timeSlider.value()], white=self.whiteLevel(), black=self.blackLevel())
        
    def autoRange(self):
        self.levelMax = float(self.image.max())
        self.levelMin = float(self.image.min())
        
        self.ui.whiteSlider.setValue(self.ui.whiteSlider.maximum())
        self.ui.blackSlider.setValue(0)
        self.imageItem.setLevels(white=self.whiteLevel(), black=self.blackLevel())
        
        self.ui.graphicsView.setRange(QtCore.QRectF(0, 0, self.image.shape[0], self.image.shape[1]), padding=0., lockAspect=True)        

    def whiteLevel(self):
        return self.levelMin + (self.levelMax-self.levelMin) * self.ui.whiteSlider.value() / self.ui.whiteSlider.maximum() 
    
    def blackLevel(self):
        return self.levelMin + ((self.levelMax-self.levelMin) / self.ui.blackSlider.maximum()) * self.ui.blackSlider.value()
        