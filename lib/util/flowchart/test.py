# -*- coding: utf-8 -*-
import sys, os
print __file__

p = os.path.dirname(os.path.abspath(__file__))
print p
p = os.path.split(p)[0]
print p
sys.path.append(p)
#import PySideImporter

from Flowchart import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *

app = QApplication([])

fc = Flowchart(terminals={
    'dataIn': ('in',),
    'dataOut': ('out',)    
})
w = fc.widget()
w.resize(800,600)
w.show()

n1 = fc.addNode('Add')
n2 = fc.addNode('Subtract')
n3 = fc.addNode('Abs')
n4 = fc.addNode('Add')

fc.dataIn.connectTo(n1.A)
fc.dataIn.connectTo(n1.B)
fc.dataIn.connectTo(n2.A)
n1.Out.connectTo(n4.A)
n1.Out.connectTo(n2.B)
n2.Out.connectTo(n3.In)
n3.Out.connectTo(n4.B)
n4.Out.connectTo(fc.dataOut)


def process(**kargs):
    return fc.process(**kargs)

#app.exec_()
#import time
#while True:
    #app.processEvents()
    #time.sleep(1e-3)


print process(dataIn=7)
