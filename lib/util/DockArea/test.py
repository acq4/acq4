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

area.moveDock(d6, 'bottom', d4)
d6.hideTitleBar()

d2.label.setTabPos(40)

#win2 = QtGui.QMainWindow()
#area2 = DockArea()
#win2.setCentralWidget(area2)
#win2.resize(800,800)


win.show()
#win2.show()

