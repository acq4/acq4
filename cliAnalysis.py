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
pyDir = os.path.split(pyfile)[0]
sys.path.append(pyDir)
from metaarray import *
from pyqtgraph.ImageView import *
from pyqtgraph.GraphicsView import *
from pyqtgraph.graphicsItems import *
from pyqtgraph.graphicsWindows import *
from pyqtgraph.PlotWidget import *
from pyqtgraph.functions import *
from Canvas import Canvas
from PyQt4 import QtCore, QtGui
from functions import *


## Initialize Qt
app = QtGui.QApplication(sys.argv)

## Configuration file to load
config = os.path.join(pyDir, 'config', 'default.cfg')

## Create Manager. This configures devices and creates the main manager window.
dm = Manager(config, sys.argv[1:])



#class EllipseItem(QtGui.QGraphicsEllipseItem, QObjectWorkaround):
#    def __init__(self, *args):
#        QObjectWorkaround.__init__(self)
#        QtGui.QGraphicsEllipseItem.__init__(self, *args)
#        
#    def mouseReleaseEvent(self, ev):
#        self.emit(QtCore.SIGNAL('clicked'), self)

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
        QtCore.QObject.connect(self.canvas.view, QtCore.SIGNAL('mouseReleased'), self.mouseClicked)
        self.plot = PlotWidget()
        self.cw.addWidget(self.canvas)
        self.cw.addWidget(self.plot)
        self.z = 0
        self.resize(800, 600)
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
        if len(dh.info()['protocol']['params']) > 0:
            dirs = dh.subDirs()
        else:
            dirs = [dh.name()]
        for d in dirs:
            d = dh[d]
            if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
               pos = d.info()['Scanner']['position']
               if 'spotSize' in d.info()['Scanner']:
                  size = d.info()['Scanner']['spotSize']
               else:
                  size = self.defaultSize
               item = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
               start = self.getLaserTime(d)
               item.setBrush(QtGui.QBrush(self.traceColor(d, start)))
               item.source = d
               self.canvas.addItem(item, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z)
               #item.connect(QtCore.SIGNAL('clicked'), self.loadTrace)
               #print pos, size
               #print item.mapRectToScene(item.boundingRect())
               self.scanItems.append(item)
            else:
               print "Skipping directory %s" %d.name()
        self.z += 1
    
    def getLaserTime(self, d):
        q = d.getFile('Laser-UV.ma').read()['QSwitch']
        return argmax(q)/q.infoCopy()[-1]['rate']
                    
        
    def clearImage(self):
        for item in self.imageItems:
            self.canvas.removeItem(item)
        self.imageItems = []
        
        
    def clearScan(self):
        for item in self.scanItems:
            self.canvas.removeItem(item)
        self.scanItems = []
        
    def loadTrace(self, item, pen=None):
        dh = item.source
        data = self.getClampData(dh)
        self.plot.plot(data, pen=pen)
        
    def getClampData(self, dh):
        data = dh['Clamp1.ma'].read()
        if data.hasColumn('Channel', 'primary'):
            data = data['Channel': 'primary']
        elif data.hasColumn('Channel', 'scaled'):
            data = data['Channel': 'scaled']
        return data
        
    def traceColor(self, dh, start = 0.5, dur = 0.1):
        data = self.getClampData(dh)
        base = data['Time': 0:(start - 0.01)]
        signal = data['Time': start:(start+dur)]
        mx = signal.max()
        mn = signal.min()
        mean = base.mean()
        std = base.std()
        red = clip((mx-mean) / std * 10, 0, 255)
        blue = clip((mean-mn) / std * 10, 0, 255)
        return QtGui.QColor(red, 0, blue, 150)
   
    def mouseClicked(self, ev):
        self.plot.clear()
        spot = self.canvas.view.items(ev.pos())
        n=0.0
        for i in spot:
            n += 1.0
            color = n/(len(spot))*0.7
            colorObj = QtGui.QColor()
            colorObj.setHsvF(color, 0.7, 1)
            pen = QtGui.QPen(colorObj)
            self.loadTrace(i, pen=pen)
        

#win = UncagingWindow()

class STDPWindow(UncagingWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        bwtop = QtGui.QSplitter()
        #hsplit = QtGui.QSplitter(bwtop)
        bwtop.setOrientation(QtCore.Qt.Horizontal)
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.cw.addWidget(bwtop)
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
        QtCore.QObject.connect(self.canvas.view, QtCore.SIGNAL('mouseReleased'), self.mouseClicked)
        self.traceplot = PlotWidget()
        self.LTPplot = PlotWidget()
        bwtop.addWidget(self.canvas)
        self.cw.addWidget(self.traceplot)
        bwtop.addWidget(self.LTPplot)
        self.z = 0
        self.resize(800, 600)
        self.show()
        self.scanItems = []
        self.imageItems = []
        
class IVWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.loadIVBtn = QtGui.QPushButton('Load I/V')
        bwl.addWidget(self.loadIVBtn)
        QtCore.QObject.connect(self.loadIVBtn, QtCore.SIGNAL('clicked()'), self.loadIV)
        self.plot = PlotWidget()
        self.cw.addWidget(self.plot)
        self.resize(800, 800)
        self.show()

    def loadIV(self):
        self.plot.clear()
        dh = getManager().currentFile
        dirs = dh.subDirs()
        c = 0.0
        for d in dirs:
            d = dh[d]
            try:
                data = d['Clamp1.ma'].read()['Channel': 'primary']
            except:
                data = d['Clamp2.ma'].read()['Channel': 'primary']
            self.plot.plot(data, pen=mkPen(hsv=[c, 0.7]))
            c += 1.0 / len(dirs)






plots = []
images = []
if QtGui.QApplication.instance() is None:
    app = QtGui.QApplication([])


def showPlot(data=None, file=None, title=None):
    global plots
    tStr = "Plot %d" % len(plots)
    if title is not None:
        tStr += " - " + title
        
    if data is None:
        data = loadMetaArray(file)
    if data.ndim == 1:
        win = PlotWindow(title=title)
        #plot = PlotWidget()
        #win.setCentralWidget(plot)
        #plot.plot(data)
        #plot.autoRange()
        win.plot(data)
        win.autoRange()
    elif data.ndim == 2:
        win = MultiPlotWindow(title=title)
        win.plot(data)
        win.autoRange()
        #gv = GraphicsView()
        #win.setCentralWidget(gv)
        #l = QtGui.QGraphicsGridLayout()
        #gv.centralWidget.setLayout(l)
        #for i in range(data.shape[0]):
            #p = PlotItem(gv.centralWidget)
            #l.addItem(p, i, 0)
            #p.plot(data[i])
            #p.autoRange()
    win.resize(800, 600)
        
        
    #win.setWindowTitle(tStr)
    plots.append({'win': win, 'data': data})
    win.show()
    return win

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
    return win
    

def dirDialog(startDir='', title="Select Directory"):
  return str(QtGui.QFileDialog.getExistingDirectory(None, title, startDir))

def fileDialog():
  return str(QtGui.QFileDialog.getOpenFileName())

def loadMetaArray(file=None):
    if file is None:
        file = fileDialog()
    return MetaArray(file=file)
    
