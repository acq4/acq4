# -*- coding: utf-8 -*-
from __future__ import print_function

import os, sys
d = os.path.split(os.path.abspath(__file__))[0]
d1 = os.path.split(d)[0]
d2 = os.path.split(d1)[0]
sys.path.extend([d1, d2])

from acq4.util.DirTreeWidget import *
from .DirTreeLoader import *
from acq4.util.DataManager import *
from acq4.util import Qt

app = Qt.QApplication([])

dm = DataManager()
dh = dm.getDirHandle(d)['testDir']


class Loader(DirTreeLoader):
    def new(self):
        print("NEW")
        return True
        
    def save(self, fh):
        open(fh.name(), 'w').write("SAVED")
        print("SAVED")
        return True
    
    def load(self, fh):
        print("LOADED:", open(fh.name()).read())
        return True
        

#w = DirTreeWidget(defaultFlags=Qt.Qt.ItemIsUserCheckable | Qt.Qt.ItemIsEnabled, defaultCheckState=False)
w = Loader(dh)
w.show()

#app.exec_()
