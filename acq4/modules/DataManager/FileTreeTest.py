from __future__ import print_function
from acq4.util import Qt
from FileTreeWidget import *
from acq4.DataManager import *


app = Qt.QApplication([])
win = Qt.QMainWindow()

cw = FileTreeWidget()
