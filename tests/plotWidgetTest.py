# -*- coding: utf-8 -*-
#import atexit
#import os

#historyPath = os.path.expanduser("~/.pyhistory")

#try:
    #import readline
#except ImportError:
    #print "Module readline not available."
#else:
    #import rlcompleter
    #readline.parse_and_bind("tab: complete")
    #if os.path.exists(historyPath):
        #readline.read_history_file(historyPath)

#def save_history(historyPath=historyPath):
    #try:
        #import readline
    #except ImportError:
        #print "Module readline not available."
    #else:
        #readline.write_history_file(historyPath)

#atexit.register(save_history)


from scipy import random
from PyQt4 import QtGui, QtCore
from lib.util.PlotWidget import *
#from PyQt4 import Qwt5 as Qwt

app = QtGui.QApplication([])
mw = QtGui.QMainWindow()
cw = QtGui.QWidget()
vl = QtGui.QVBoxLayout()
cw.setLayout(vl)
mw.setCentralWidget(cw)
mw.show()

p1 = PlotWidget(cw)
vl.addWidget(p1)
p2 = PlotWidget(cw)
vl.addWidget(p2)


data = array([1,4,2,5,3,6,4,7,5,6,3,4,5,32,2,21,34,65,4,3,2,5,4,6,6,3,2,434])
#c1 = Qwt.QwtPlotCurve()
#c1.setData(range(len(data)), data)
#c1.attach(p1)
c2 = PlotCurve()
c2.setData([1,2,3,4,5,6,7,8], [1,2,10,4,3,2,4,1])
c2.attach(p2)

def updateData():
    global data
    data = random.random(len(data))
    data[10:13] += .5
    data[18] += 2
    data[10:13] *= 5
    data[18] *= 20
    #c1.setData(range(len(data)), data)
    
    p1.plot(data)
    
t = QtCore.QTimer()
QtCore.QObject.connect(t, QtCore.SIGNAL('timeout()'), updateData)
t.start(200)


