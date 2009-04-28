# -*- coding: utf-8 -*-
from lib.util.generator.StimGenerator import *
from PyQt4 import QtCore, QtGui

app = QtGui.QApplication([])
w = StimGenerator()
w.show()
w.loadState({'waveform': 'steps([0,1,2,3,4], [0,i,i+1,i,0])', 'sequence': 'i = 35; 10:100:1.1:lr'})

def run():
    print w.getSingle(1, 5)
    for i in range(len(w.paramSpace()['i'][1])):
        print w.getSingle(1, 5, {'i': i})
#app.exec_()
