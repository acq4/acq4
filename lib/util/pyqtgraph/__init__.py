# -*- coding: utf-8 -*-
### import all the goodies and add some helper functions for easy CLI use

from functions import *
from graphicsItems import *
from graphicsWindows import *
#import PlotWidget
#import ImageView
from Qt import QtGui
from Point import Point
from Transform import Transform

if not hasattr(QtCore, 'Signal'):  ## for pyside compatibility
    QtCore.Signal = QtCore.pyqtSignal
    QtCore.Slot = QtCore.pyqtSlot


plots = []
images = []
QAPP = None

def plot(*args, **kargs):
    mkQApp()
    if 'title' in kargs:
        w = PlotWindow(title=kargs['title'])
        del kargs['title']
    else:
        w = PlotWindow()
    w.plot(*args, **kargs)
    plots.append(w)
    w.show()
    return w
    
def image(*args, **kargs):
    mkQApp()
    w = ImageWindow(*args, **kargs)
    images.append(w)
    w.show()
    return w
show = image  ## for backward compatibility
    
    
def mkQApp():
    if QtGui.QApplication.instance() is None:
        global QAPP
        QAPP = QtGui.QApplication([])