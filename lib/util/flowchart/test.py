# -*- coding: utf-8 -*-
import sys, os
print __file__

p = os.path.dirname(os.path.abspath(__file__))
p = os.path.split(p)[0]
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

n1 = fc.createNode('Add')
n2 = fc.createNode('Subtract')
n3 = fc.createNode('Abs')
n4 = fc.createNode('Add')

fc.connect(fc.dataIn, n1.A)
fc.connect(fc.dataIn, n1.B)
fc.connect(fc.dataIn, n2.A)
fc.connect(n1.Out, n4.A)
fc.connect(n1.Out, n2.B)
fc.connect(n2.Out, n3.In)
fc.connect(n3.Out, n4.B)
fc.connect(n4.Out, fc.dataOut)


def process(**kargs):
    return fc.process(**kargs)

#app.exec_()
#import time
#while True:
    #app.processEvents()
    #time.sleep(1e-3)


print process(dataIn=7)
