import sys, os
md = os.path.abspath(os.path.split(__file__)[0])
sys.path = [os.path.join(md, '..', '..', 'util')] + sys.path

dataFile = "CochlearNucleus/images/cochlear_nucleus.ma"
labelFile = "CochlearNucleus/images/cochlear_nucleus_label.ma"

from PyQt4 import QtCore, QtGui
import pyqtgraph as pg
import numpy as np
import builderTemplate
import metaarray
import debug

QtGui.QApplication.setGraphicsSystem('raster')
app = QtGui.QApplication([])

win = QtGui.QMainWindow()
cw = QtGui.QWidget()
win.setCentralWidget(cw)
ui = builderTemplate.Ui_Form()
ui.setupUi(cw)
win.show()
win.resize(800,600)

data = metaarray.MetaArray(file=dataFile, mmap=True)
## data must have axes (anterior, dorsal, right)
if not os.path.exists(labelFile):
    label = metaarray.MetaArray(np.zeros(data.shape[:-1], dtype=np.uint16), info=data.infoCopy()[:3])
else:
    label = metaarray.MetaArray(file=labelFile)
labelCache = None    
#ui.view.enableMouse()
#ui.view.setAspectLocked(True)

vb = pg.ViewBox()
ui.view.setCentralItem(vb)
vb.setAspectLocked(True)
vb.invertY(False)


dataImg = pg.ImageItem()
labelImg = pg.ImageItem(mode=QtGui.QPainter.CompositionMode_Plus)
labelImg.setZValue(10)
labelImg.setOpacity(1)
vb.addItem(dataImg)
vb.addItem(labelImg)


def connectSignals():
    for r in [ui.rightRadio, ui.dorsalRadio, ui.rostralRadio]:
        r.toggled.connect(imageChanged)
    ui.zSlider.valueChanged.connect(updateImage)
    ui.radiusSpin.valueChanged.connect(updateKernel)


def init():
    connectSignals()
    updateKernel()

def keyPressEvent(ev):
    k = ev.key()
    mod = ev.modifiers()
    if k == QtCore.Qt.Key_Right:
        if mod & QtCore.Qt.ControlModifier:
            copyLabel(1)
        ui.zSlider.setValue(ui.zSlider.value()+1)
    elif k == QtCore.Qt.Key_Left:
        if mod & QtCore.Qt.ControlModifier:
            copyLabel(-1)
        ui.zSlider.setValue(ui.zSlider.value()-1)
    elif k == QtCore.Qt.Key_Equal:
        ui.radiusSpin.setValue(ui.radiusSpin.value()+1)
    elif k == QtCore.Qt.Key_Minus:
        ui.radiusSpin.setValue(ui.radiusSpin.value()-1)
    elif k == QtCore.Qt.Key_Space:
        labelImg.setVisible(not labelImg.isVisible())
    else:
        ev.ignore()
cw.keyPressEvent = keyPressEvent


currentPos = [0,0,0]
zAxis = 0

def draw(src, dst, mask, srcSlice, dstSlice, ev):
    p = debug.Profiler('draw', disabled=True)
    l = displayLabel.view(np.ndarray)[ui.zSlider.value()]
    p.mark('1')
    mod = ev.modifiers()
    mask = mask[srcSlice]
    src = src[srcSlice]
    if mod & QtCore.Qt.ShiftModifier:
        src = 1-src
    #l[dstSlice] = l[dstSlice] * (1-mask) + src * mask
    p.mark('2')
    l[dstSlice] |= src * 2**ui.labelSpin.value()
    p.mark('3')
    updateLabelImage(dstSlice)
    p.mark('4')
    p.finish()
    

def copyLabel(n):
    pass

def updateImage():
    currentPos[zAxis] = ui.zSlider.value()
    dataImg.updateImage(displayData.view(np.ndarray)[ui.zSlider.value()], copy=False)
    #labelImg.updateImage(displayLabel.view(np.ndarray)[ui.zSlider.value()], copy=False, white=10, black=0)
    updateLabelImage()

def updateLabelImage(sl=None):
    #p = debug.Profiler('updateLabelImage', disabled=True)
    global labelCache
    if sl is None or labelCache is None:
        sl = (slice(None), slice(None))
    l = displayLabel.view(np.ndarray)[ui.zSlider.value()]
    #p.mark('1')
    lsl = l[sl]
    img = np.empty(lsl.shape+(3,), dtype=np.ubyte)
    #p.mark('2')
    img.fill(0)
    #p.mark('3')
    img[...,0] += (lsl&1>0) * 200
    img[...,1] += (lsl&2>0) * 200
    img[...,2] += (lsl&4>0) * 200
    #p.mark('4')
    if labelCache is None:
        labelCache = img
        labelImg.updateImage(labelCache, copy=False, white=255, black=0)
    else:
        labelCache[sl] = img
        labelImg.updateImage()
        #labelImg.updateImage(labelCache, copy=False, white=255, black=0)
        #print repr(labelCache.data), repr(labelImg.image.data)
    #p.mark('5')
    #p.mark('6')
    #p.finish()

    

def imageChanged():
    global zAxis, displayData, displayLabel, labelCache
    labelCache = None
    if ui.rightRadio.isChecked():
        axes = ('right', 'anterior', 'dorsal')
        zAxis = 0
    elif ui.dorsalRadio.isChecked():
        axes = ('dorsal', 'right', 'anterior')
        zAxis = 1
    else:
        axes = ('anterior', 'right', 'dorsal')
        zAxis = 2
        
    displayData = data.transpose(axes)
    displayLabel = label.transpose(axes)
    ui.zSlider.setMaximum(displayData.shape[0]-1)
    ui.zSlider.setValue(currentPos[zAxis])
    
    updateImage()
    #vb.setRange(dataImg.boundingRect())
    vb.autoRange()


def updateKernel():
    global drawKernel
    r = ui.radiusSpin.value()+1
    d = (r*2) - 1
    x = np.array([range(d)])
    y = x.transpose()
    drawKernel = (np.sqrt((x-r+1)**2 + (y-r+1)**2) < r-1).astype(np.ubyte)
    labelImg.setDrawKernel(drawKernel, mask=drawKernel, center=(r-1,r-1), mode=draw)
    

init()
imageChanged()