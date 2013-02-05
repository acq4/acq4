# -*- coding: utf-8 -*-
import initExample ## Add path to library (just for examples; you do not need this)

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np

pg.mkQApp()

spw = pg.ScatterPlotWidget()
spw.show()

data = np.array([
    (1, 1, 3, 4),
    (2, 3, 3, 7),
    (3, 2, 5, 2),
    (4, 4, 6, 9),
    (5, 3, 6, 7),
    (6, 5, 2, 6),
    (7, 5, 7, 2),
    ], dtype=[('col1', float), ('col2', float), ('col3', int), ('col4', int)])

spw.setFields([
    ('col1', 'm'),
    ('col2', 'm'),
    ('col3', ''),
    ('col4', ''),
    ])
    
spw.setData(data)


## Start Qt event loop unless running in interactive mode or using pyside.
if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()
