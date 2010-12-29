import sys
sys.path.append('..')
from PyQt4 import QtCore, QtGui
from DockArea import *
from Dock import *

app = QtGui.QApplication([])
win = QtGui.QMainWindow()
area = DockArea()
win.setCentralWidget(area)
win.resize(800,800)
from Dock import Dock
d1 = Dock("Dock1")
d2 = Dock("Dock2")
d3 = Dock("Dock3")
d4 = Dock("Dock4")
d5 = Dock("Dock5")
d6 = Dock("Dock6")
area.addDock(d1, 'left')
area.addDock(d2, 'right')
area.addDock(d3, 'bottom')
area.addDock(d4, 'right')
area.addDock(d5, 'left', d1)
area.addDock(d6, 'top', d4)

area.moveDock(d6, 'above', d4)
d3.hideTitleBar()

for d in [d1, d2, d3, d4, d5, d6]:
    w = QtGui.QWidget()
    l = QtGui.QVBoxLayout()
    w.setLayout(l)
    btns = []
    for i in range(4):
        btns.append(QtGui.QPushButton("%s Button %d"%(d.name(), i)))
        l.addWidget(btns[-1])
    d.w = (w, l, btns)
    d.addWidget(w)

s = area.saveState()


#print "\n\n-------restore----------\n\n"
area.restoreState(s)


#d6.container().setCurrentIndex(0)
#d2.label.setTabPos(40)

#win2 = QtGui.QMainWindow()
#area2 = DockArea()
#win2.setCentralWidget(area2)
#win2.resize(800,800)


win.show()
#win2.show()

