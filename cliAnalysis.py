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
from lib.analysis import *


### Use CLI history
import atexit
import os
historyPath = os.path.expanduser("~/.pyhistory")
try:
    import readline
except ImportError:
    print "Module readline not available."
else:
    import rlcompleter
    readline.parse_and_bind("tab: complete")
    if os.path.exists(historyPath):
        readline.read_history_file(historyPath)
def save_history(historyPath=historyPath):
    try:
        import readline
    except ImportError:
        print "Module readline not available."
    else:
        readline.write_history_file(historyPath)
atexit.register(save_history)


## Initialize Qt
app = QtGui.QApplication(sys.argv)

## Configuration file to load
config = os.path.join(pyDir, 'config', 'default.cfg')

## Create Manager. This configures devices and creates the main manager window.
dm = Manager(config, sys.argv[1:])


## Start Qt event loop unless running in interactive mode.
try:
    assert sys.flags.interactive == 1
    print "Interactive mode; not starting event loop."
    
    ## import some things useful on the command line
    from debug import *
    from pyqtgraph.graphicsWindows import *
    from functions import *
    
except:
    ##Make sure pythin core runs requently enough to allow debugger interaction.
    timer = QtCore.QTimer()
    QtCore.QObject.connect(timer, QtCore.SIGNAL('timeout()'), lambda: 1+1)
    timer.start(200)
    
    print "Starting Qt event loop.."
    app.exec_()
    print "Qt event loop exited."





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


class PSPWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.loadTraceBtn = QtGui.QPushButton('Load Trace')
        bwl.addWidget(self.loadTraceBtn)
        QtCore.QObject.connect(self.loadTraceBtn, QtCore.SIGNAL('clicked()'), self.loadTrace)
        self.plot = PlotWidget()
        self.cw.addWidget(self.plot)
        self.resize(800, 800)
        self.show()

    def loadTrace(self):
        self.plot.clear()
        fh = getManager().currentFile
        try:
            data = d['Clamp1.ma'].read()['Channel': 'primary']
        except:
            data = d['Clamp2.ma'].read()['Channel': 'primary']
        self.plot.plot(data)
        
        



plots = []
images = []
if QtGui.QApplication.instance() is None:
    app = QtGui.QApplication([])


def showPlot(data=None, x=None, file=None, title=None):
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
        win.plot(data, x)
        win.autoRange()
    elif data.ndim == 2:
        win = MultiPlotWindow(title=title)
        win.plot(data, x)
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
    
