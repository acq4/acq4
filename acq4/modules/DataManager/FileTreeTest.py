from PyQt4 import QtCore, QtGui
from FileTreeWidget import *
from acq4.DataManager import *


app = QtGui.QApplication([])
win = QtGui.QMainWindow()

cw = FileTreeWidget()
