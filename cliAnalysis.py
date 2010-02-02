#!/usr/bin/python -i
# -*- coding: utf-8 -*-
"""
cliAnalysis.py - Command line analysis interface 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Run in interactive python. Useful for accessing data for manual analysis.
"""

from lib.Manager import *

import sys, os
pyfile = __file__
if pyfile[0] != '/':
   pyfile =  os.path.join(os.getcwd(), pyfile)
sys.path.append(os.path.split(pyfile)[0])
from lib.util.metaarray import *
from lib.util.pyqtgraph.ImageView import *
from lib.util.pyqtgraph.GraphicsView import *
from lib.util.pyqtgraph.graphicsItems import *
from lib.util.pyqtgraph.PlotWidget import *
from lib.util.Canvas import Canvas
from PyQt4 import QtCore, QtGui
from lib.util.functions import *


## Initialize Qt
app = QtGui.QApplication(sys.argv)

## Configuration file to load
config = 'config/default.cfg'

## Create Manager. This configures devices and creates the main manager window.
dm = Manager(config, sys.argv[1:])



class EllipseItem(QtGui.QGraphicsEllipseItem, QObjectWorkaround):
    def __init__(self, *args):
        QObjectWorkaround.__init__(self)
        QtGui.QGraphicsEllipseItem.__init__(self, *args)
        
        
    def mouseReleaseEvent(self, ev):
        self.emit(QtCore.SIGNAL('clicked'), self)

class UncagingWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.addImgBtn = QtGui.QPushButton('Add Image')
        self.addScanBtn = QtGui.QPushButton('Add Scan')
        self.clearImgBtn = QtGui.QPushButton('Clear Images')
        self.clearScanBtn = QtGui.QPushButton('Clear Scans')
        self.defaultSize = 150e-6
        bwl.addWidget(self.addImgBtn)
        bwl.addWidget(self.clearImgBtn)
        bwl.addWidget(self.addScanBtn)
        bwl.addWidget(self.clearScanBtn)
        QtCore.QObject.connect(self.addImgBtn, QtCore.SIGNAL('clicked()'), self.addImage)
        QtCore.QObject.connect(self.addScanBtn, QtCore.SIGNAL('clicked()'), self.addScan)
        QtCore.QObject.connect(self.clearImgBtn, QtCore.SIGNAL('clicked()'), self.clearImage)
        QtCore.QObject.connect(self.clearScanBtn, QtCore.SIGNAL('clicked()'), self.clearScan)
        #self.layout = QtGui.QVBoxLayout()
        #self.cw.setLayout(self.layout)
        self.canvas = Canvas()
        self.plot = PlotWidget()
        self.cw.addWidget(self.canvas)
        self.cw.addWidget(self.plot)
        self.z = 0
        self.resize(800, 800)
        self.show()
        self.scanItems = []
        self.imageItems = []
        
    def addImage(self, img=None):
        if img is None:
            fd = getManager().currentFile
            img = fd.read()
        if 'imagePosition' in fd.info():
            ps = fd.info()['pixelSize']
            pos = fd.info()['imagePosition']
        else:
            info = img.infoCopy()[-1]
            ps = info['pixelSize']
            pos = info['imagePosition']
            
        img = img.astype(ndarray)
        if img.ndim == 3:
            img = img.max(axis=0)
        #print pos, ps, img.shape, img.dtype, img.max(), img.min()
        item = ImageItem(img)
        self.canvas.addItem(item, pos, scale=ps, z=self.z)
        self.z += 1
        self.imageItems.append(item)

    def addScan(self):
        dh = getManager().currentFile
        dirs = dh.subDirs()
        for d in dirs:
            d = dh[d]
            pos = d.info()['Scanner']['position']
            if 'spotSize' in d.info()['Scanner']:
               size = d.info()['Scanner']['spotSize']
            else:
               size = self.defaultSize
            item = EllipseItem(0, 0, 1, 1)
            item.setBrush(QtGui.QBrush(self.traceColor(d)))
            item.source = d
            self.canvas.addItem(item, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z)
            item.connect(QtCore.SIGNAL('clicked'), self.loadTrace)
            #print pos, size
            #print item.mapRectToScene(item.boundingRect())
            self.scanItems.append(item)
        self.z += 1
        
    def clearImage(self):
        for item in self.imageItems:
            self.canvas.removeItem(item)
        self.imageItems = []
        
        
    def clearScan(self):
        for item in self.scanItems:
            self.canvas.removeItem(item)
        self.scanItems = []
        
    def loadTrace(self, item):
        dh = item.source
        data = dh['Clamp1.ma'].read()['Channel': 'primary']
        self.plot.clear()
        self.plot.plot(data)
        
    def traceColor(self, dh):
        data = dh['Clamp1.ma'].read()['Channel': 'primary']
        base = data['Time': 0.4:0.49]
        signal = data['Time': 0.5:0.6]
        mx = signal.max()
        mn = signal.min()
        mean = base.mean()
        std = base.std()
        red = clip((mx-mean) / std * 10, 0, 255)
        blue = clip((mean-mn) / std * 10, 0, 255)
        return QtGui.QColor(red, 0, blue, 150)
        

win = UncagingWindow()










plots = []
images = []
if QtGui.QApplication.instance() is None:
    app = QtGui.QApplication([])


def showPlot(data=None, file=None, title=None):
    global plots
    if data is None:
        data = loadMetaArray(file)
    win = QtGui.QMainWindow()
    win.resize(800, 600)
    if data.ndim == 1:
        plot = PlotWidget()
        win.setCentralWidget(plot)
        plot.plot(data)
        plot.autoRange()
    elif data.ndim == 2:
        gv = GraphicsView()
        win.setCentralWidget(gv)
        l = QtGui.QGraphicsGridLayout()
        gv.centralWidget.setLayout(l)
        for i in range(data.shape[0]):
            p = PlotItem(gv.centralWidget)
            l.addItem(p, i, 0)
            p.plot(data[i])
            p.autoRange()
        
        
    tStr = "Plot %d" % len(plots)
    if title is not None:
        tStr += " - " + title
    win.setWindowTitle(tStr)
    plots.append({'win': win, 'data': data})
    win.show()

def showImage(data=None, file=None, title=None):
    global images
    if data is None:
        data = loadMetaArray(file)
    win = QtGui.QMainWindow()
    win.resize(800, 600)
    imv = ImageView()
    win.setCentralWidget(imv)
    imv.setImage(data.view(ndarray))
    
    tStr = "Image %d" % len(plots)
    if title is not None:
        tStr += " - " + title
    win.setWindowTitle(tStr)
    images.append({'win': win, 'data': data})
    win.show()
    

def dirDialog(startDir='', title="Select Directory"):
  return str(QtGui.QFileDialog.getExistingDirectory(None, title, startDir))

def fileDialog():
  return str(QtGui.QFileDialog.getOpenFileName())

def loadMetaArray(file=None):
    if file is None:
        file = fileDialog()
    return MetaArray(file=file)
    
