# -*- coding: utf-8 -*-

import os, sys
d = os.path.split(os.path.abspath(__file__))[0]
d1 = os.path.split(d)[0]
d2 = os.path.split(d1)[0]
sys.path.extend([d1, d2])

from DirTreeWidget import *
from DataManager import *

app = QtGui.QApplication([])

dm = DataManager()
dh = dm.getDirHandle(d2)

w = DirTreeWidget(defaultFlags=QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled, defaultCheckState=False)
w.setRoot(dh)
w.show()
