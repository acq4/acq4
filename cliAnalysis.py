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
#from pyqtgraph.ImageView import *
#from pyqtgraph.GraphicsView import *
#from pyqtgraph.graphicsItems import *
#from pyqtgraph.graphicsWindows import *
#from pyqtgraph.PlotWidget import *
#from pyqtgraph.functions import *
from pyqtgraph import *
from Canvas import Canvas
from PyQt4 import QtCore, QtGui
from functions import *
#from lib.analysis import *


## Disable long-term storage of exception stack frames
## This fixes a potentially major memory leak, but
## may break some debuggers.
import disableExceptionStorage

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


#w = UncagingWindow()

#from lib.analysis.analyzer import *
#d = os.path.dirname(os.path.abspath(__file__))
#dh = dm.dirHandle(os.path.join(d, 'lib', 'analysis', 'protocols'))
#w1 = Analyzer(dh)
#w2 = Analyzer(dh)

#from lib.analysis.mosaicEditor import *
#w = MosaicEditor()
#win = UncagingWindow() #### IMPORTANT: the name of the UncagingWindow needs to be win in order for an AnalysisPlotWindow to get data from it - need to fix this, obviously
#w = AnalysisPlotWindow()
#cm = CellMixer()


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
    def donothing(*args):
        x = 1+1
    timer.connect(timer, QtCore.SIGNAL("timeout()"), donothing)
    timer.start(200)
    
    print "Starting Qt event loop.."
    app.exec_()
    print "Qt event loop exited."





        
        



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
        win.plot(y=data, x=x)
        win.autoRange()
    elif data.ndim == 2:
        win = MultiPlotWindow(title=title)
        win.plot(y=data, x=x)
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
    
