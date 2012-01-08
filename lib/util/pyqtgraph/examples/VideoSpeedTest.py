#!/usr/bin/python
# -*- coding: utf-8 -*-
## Add path to library (just for examples; you do not need this)
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


from PyQt4 import QtGui, QtCore
import numpy as np
import pyqtgraph as pg
from pyqtgraph import RawImageWidget

#QtGui.QApplication.setGraphicsSystem('raster')
app = QtGui.QApplication([])
#mw = QtGui.QMainWindow()
#mw.resize(800,800)



#w = pg.GraphicsWindow()
#v = w.addViewBox()
#v.setAspectLocked()
#v.setRange(QtCore.QRectF(0, 0, 512, 512))
#im = pg.ImageItem()
#v.addItem(im)
im = RawImageWidget()
im.show()
im.resize(512, 512)


label = QtGui.QLabel()
label.show()
label.resize(100, 20)
data = np.clip(np.random.normal(size=(20,512,512), loc=128, scale=64), 0, 255).astype(np.ubyte)
ptr = 0
lastTime = time.time()
fps = None
def update():
    global im, data, ptr, label, lastTime, fps
    im.setImage(data[ptr%20], scale=2)
    ptr += 1
    now = time.time()
    dt = now - lastTime
    lastTime = now
    if fps is None:
        fps = 1.0/dt
    else:
        s = np.clip(dt*3., 0, 1)
        fps = fps * (1-s) + (1.0/dt) * s
    label.setText('%0.2f fps' % fps)
    app.processEvents()  ## force complete redraw for every plot
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(0)
    


## Start Qt event loop unless running in interactive mode.
if sys.flags.interactive != 1:
    app.exec_()
