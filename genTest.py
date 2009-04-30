# -*- coding: utf-8 -*-
from lib.util.generator.StimGenerator import *
from PyQt4 import QtCore, QtGui
from lib.util.SequenceRunner import *
app = QtGui.QApplication([])
w = StimGenerator()
w.show()
w.loadState({
    'waveform': 'steps([0,1,2,3,4], [0,i,i+j,j,0])', 
    'sequence': 'i = 35; 10:100/4\nj = 0; 0:10/4'
})

def run(n=5, r=1):
    print "\nSingle:"
    print w.getSingle(r, n)
    print "\nSequence:"
    ps = w.listSequences()
    params = {}
    for k in ps:
        params[k] = range(ps[k])
    print runSequence(lambda args: w.getSingle(r, n, args), params, params.keys(), passHash=True)
    
def single(r, n, args):
    return w.getSingle(r, n, args)
    
run()
#app.exec_()
