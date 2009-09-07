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
mw.resize(800, 600)


p1 = PlotWidget(cw, "Plot1")
vl.addWidget(p1)
p2 = PlotWidget(cw, "Plot2")
vl.addWidget(p2)
p3 = PlotWidget(cw, "Plot3")
vl.addWidget(p3)


#c1 = Qwt.QwtPlotCurve()
#c1.setData(range(len(data)), data)
#c1.attach(p1)
#c2 = PlotCurve()
#c2.setData([1,2,3,4,5,6,7,8], [1,2,10,4,3,2,4,1])
#c2.attach(p2)

def rand(n):
    data = random.random(n)
    data[int(n*0.1):int(n*0.13)] += .5
    data[int(n*0.18)] += 2
    data[int(n*0.1):int(n*0.13)] *= 5
    data[int(n*0.18)] *= 20
    #c1.setData(range(len(data)), data)
    return data, arange(n, n+len(data)) / float(n)
    

def updateData():
    yd, xd = rand(10000)
    p1.plot(yd, x=xd, clear=True)

yd, xd = rand(10000)
p2.plot(yd * 1000, x=xd)
for i in [1,2]:
    for j in range(3):
        yd, xd = rand(1000)
        p3.plot(yd * 100000 * i, x=xd, params={'repetitions': j, 'scale': i})

t = QtCore.QTimer()
QtCore.QObject.connect(t, QtCore.SIGNAL('timeout()'), updateData)
#t.start(200)
updateData()

