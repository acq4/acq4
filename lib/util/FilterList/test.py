# -*- coding: utf-8 -*-
import sys
sys.path.append('..')

from PyQt4.QtGui import *
from PyQt4 import QtCore
from FilterList import *
from pyqtgraph.PlotWidget import *
from numpy import *

app = QApplication([])
win = QMainWindow()
cw = QWidget()
hl = QHBoxLayout()
cw.setLayout(hl)

fl = FilterList()
fl.restoreState([{'name': 'DN1', 'type': 'Denoise', 'enabled': False, 'opts': {'threshold': 12}}])
fl.addFilter('Bessel', cutoff=2000)


hl.addWidget(fl)

vw = QWidget()
hl.addWidget(vw)
vl = QVBoxLayout()
vw.setLayout(vl)

p1 = PlotWidget(name='Plot 1')
p2 = PlotWidget(name='Plot 2')
vl.addWidget(p1)
vl.addWidget(p2)
p1.setXLink(p2)


win.setCentralWidget(cw)
win.show()

data = random.random(10000)
data[5000:6000] += 2
data[5500] += 20
data[6000:7000] -= 3
data += linspace(1, 3, 10000)
data += sin(linspace(0, 15, 10000))
for i in range(9):
    data[1000+i*100] += 1.5**i
    data[2000+i*100:2000+i*101] += 3
    data[4000+i*100:4500+i*100] += 1.5**i * exp(-linspace(0, exp(1), 500))
    data[3000+i*100:3500+i*100] += 1.5**i * exp(-linspace(0, exp(1)*5, 500))
    
data = MetaArray(data, info=[{'name': 'Time', 'values': linspace(0, 1, 10000)}])

p1.plot(data)

def replot():
    d2 = fl.processData(data.copy())
    p2.plot(d2, clear=True)
    
#QtCore.QObject.connect(fl, QtCore.SIGNAL('changed'), replot)
fl.sigChanged.connect(replot)

#app.exec_()
