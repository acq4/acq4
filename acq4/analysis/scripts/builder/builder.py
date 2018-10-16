from __future__ import print_function
import sys, os
md = os.path.abspath(os.path.split(__file__)[0])
sys.path = [os.path.join(md, '..', '..', 'util')] + sys.path

dataFile = "../../atlas/CochlearNucleus/images/cochlear_nucleus.ma"
labelFile = "../../atlas/CochlearNucleus/images/cochlear_nucleus_label.ma"

from acq4.util import Qt
import acq4.pyqtgraph as pg
#import acq4.pyqtgraph.ColorButton as ColorButton
#import acq4.pyqtgraph.ProgressDialog as ProgressDialog
import numpy as np
import builderTemplate
import acq4.util.metaarray as metaarray
import acq4.util.debug as debug
import user

Qt.QApplication.setGraphicsSystem('raster')
app = Qt.QApplication([])

win = Qt.QMainWindow()
cw = Qt.QWidget()
win.setCentralWidget(cw)
ui = builderTemplate.Ui_Form()
ui.setupUi(cw)
win.show()
win.resize(800,600)

ui.labelTree.header().setResizeMode(Qt.QHeaderView.ResizeToContents)

data = metaarray.MetaArray(file=dataFile, mmap=True)
## data must have axes (anterior, dorsal, right)
if not os.path.exists(labelFile):
    label = metaarray.MetaArray(np.zeros(data.shape[:-1], dtype=np.uint16), info=data.infoCopy()[:3] + [{'labels': {}}])
    label.write(labelFile, mappable=True)
label = metaarray.MetaArray(file=labelFile, mmap=True, writable=True)

    
    
labelCache = None    
labelInfo = {}
#ui.view.enableMouse()
#ui.view.setAspectLocked(True)

vb = pg.ViewBox()
ui.view.setCentralItem(vb)
vb.setAspectLocked(True)
vb.invertY(False)


dataImg = pg.ImageItem()
labelImg = pg.ImageItem() # mode=Qt.QPainter.CompositionMode_Plus)
#labelImg.setCompositionMode(Qt.QPainter.CompositionMode_Overlay)
labelImg.setZValue(10)
labelImg.setOpacity(1)
vb.addItem(dataImg)
vb.addItem(labelImg)


def connectSignals():
    for r in [ui.rightRadio, ui.dorsalRadio, ui.rostralRadio]:
        r.toggled.connect(imageChanged)
    ui.zSlider.valueChanged.connect(updateImage)
    ui.radiusSpin.valueChanged.connect(updateKernel)
    ui.greyCheck.toggled.connect(updateImage)
    ui.labelSlider.valueChanged.connect(imageChanged)
    ui.labelTree.itemChanged.connect(itemChanged)
    ui.labelTree.currentItemChanged.connect(itemSelected)
    ui.overlayCheck.toggled.connect(overlayToggled)

def init():
    connectSignals()
    updateKernel()

    labelData = label._info[-1]['labels']
    d = dict([(x['id'], x) for x in labelData])
    keys = list(d.keys())
    keys.sort()
    for k in keys:
        addLabel(d[k])


def keyPressEvent(ev):
    k = ev.key()
    mod = ev.modifiers()
    if k == Qt.Qt.Key_Right:
        if mod & Qt.Qt.ControlModifier:
            copyLabel(1)
        ui.zSlider.setValue(ui.zSlider.value()+1)
    elif k == Qt.Qt.Key_Left:
        if mod & Qt.Qt.ControlModifier:
            copyLabel(-1)
        ui.zSlider.setValue(ui.zSlider.value()-1)
    elif k == Qt.Qt.Key_Equal:
        ui.radiusSpin.setValue(ui.radiusSpin.value()+1)
    elif k == Qt.Qt.Key_Minus:
        ui.radiusSpin.setValue(ui.radiusSpin.value()-1)
    elif k == Qt.Qt.Key_Space:
        if labelImg.isVisible():
            labelImg.setVisible(False)
        else:
            updateLabelImage()
            labelImg.setVisible(True)
    elif k == Qt.Qt.Key_G:
        ui.greyCheck.toggle()
    else:
        ev.ignore()
cw.keyPressEvent = keyPressEvent


currentPos = [0,0,0]
zAxis = 0

def draw(src, dst, mask, srcSlice, dstSlice, ev):
    addLabel()
    
    #p = debug.Profiler('draw', disabled=True)
    l = displayLabel.view(np.ndarray)[ui.zSlider.value()]
    #p.mark('1')
    mod = ev.modifiers()
    mask = mask[srcSlice]
    src = src[srcSlice].astype(l.dtype)
    if mod & Qt.Qt.ShiftModifier:
        #src = 1-src
        l[dstSlice] &= ~(src * 2**ui.labelSpin.value())
    #l[dstSlice] = l[dstSlice] * (1-mask) + src * mask
    #p.mark('2')
    else:
        l[dstSlice] |= src * 2**ui.labelSpin.value()
    #p.mark('3')
    updateLabelImage(dstSlice)
    #p.mark('4')
    #p.finish()
    
def addLabel(info=None):
    global labelInfo
    create = False
    if info is None:
        create = True
        l = ui.labelSpin.value()
        if l in labelInfo:
            return
        info = {
            'visible': True,
            'name': 'label',
            'color': pg.intColor(len(labelInfo), 16),
            'id': l
        }
    else:
        info = info.copy()
        info['color'] = pg.mkColor(info['color'])
    
    l = info['id']
    item = Qt.QTreeWidgetItem([str(l), info['name'], ''])
    item.setFlags(item.flags() | Qt.Qt.ItemIsEditable | Qt.Qt.ItemIsUserCheckable)
    if info['visible']:
        item.setCheckState(0, Qt.Qt.Checked)
    else:
        item.setCheckState(0, Qt.Qt.Unchecked)
    btn = pg.ColorButton(color=info['color'])
    ui.labelTree.addTopLevelItem(item)
    ui.labelTree.setItemWidget(item, 2, btn)
    labelInfo[l] = {'item': item, 'btn': btn}
    btn.sigColorChanged.connect(itemChanged)
    btn.sigColorChanging.connect(imageChanged)
    
    if create:
        writeMeta()


def overlayToggled(b):
    if b:
        labelImg.setCompositionMode(Qt.QPainter.CompositionMode_Overlay)
    else:
        labelImg.setCompositionMode(Qt.QPainter.CompositionMode_SourceOver)
    updateImage()

def itemChanged(*args):
    imageChanged()
    writeMeta()
    
def writeMeta():
    meta = []
    for k, v in labelInfo.items():
        meta.append( {
            'id': k,
            'name': str(v['item'].text(1)),
            'color': pg.colorStr(v['btn'].color()),
            'visible': v['item'].checkState(0) == Qt.Qt.Checked
        } )
    label._info[-1]['labels'] = meta
    label.writeMeta(labelFile)

def itemSelected(item):
    ui.labelTree.editItem(item, 1)

def copyLabel(n):
    i1 = ui.zSlider.value()
    i2 = i1 + n
    if i2 < 0 or i2 > displayLabel.shape[0]:
        return
    #displayLabel[i2] &= ~mask
    #displayLabel[i2] |= displayLabel[i1] & mask
    mask = np.uint16(2**ui.labelSpin.value())
    
    displayLabel[i2] = (displayLabel[i1] & mask) | (displayLabel[i2] & ~mask)

def updateImage():
    currentPos[zAxis] = ui.zSlider.value()
    if ui.greyCheck.isChecked():
        img = displayData.view(np.ndarray)[ui.zSlider.value()].mean(axis=2)
    else:
        img = displayData.view(np.ndarray)[ui.zSlider.value()]
    dataImg.setImage(img, levels=None)
    #labelImg.updateImage(displayLabel.view(np.ndarray)[ui.zSlider.value()], copy=False, white=10, black=0)
    if labelImg.isVisible():
        updateLabelImage()

def renderLabels(z, sl=None, overlay=False):
    #p = debug.Profiler('updateLabelImage', disabled=True)
    if sl is None:
        sl = (slice(None), slice(None))

    l = displayLabel.view(np.ndarray)[z]
    #p.mark('1')
    lsl = l[sl]
    img = np.empty(lsl.shape+(4,), dtype=np.uint16)
    
    #img.fill(128)
    img.fill(0)
    val = ui.labelSlider.value()/128.
    
    for k, v in labelInfo.items():
        if not v['item'].checkState(0) == Qt.Qt.Checked:
            continue
        c = pg.colorTuple(v['btn'].color())
        mask = (lsl&(2**k) > 0)
        alpha = c[3]/255. * val
        img[mask] *= 1.0 - alpha
        img[...,0] += mask * int(c[0] * alpha)
        img[...,1] += mask * int(c[1] * alpha)
        img[...,2] += mask * int(c[2] * alpha)
        #img[...,0] += mask * int(c[0] * val)
        #img[...,1] += mask * int(c[1] * val)
        #img[...,2] += mask * int(c[2] * val)
        img[...,3] += mask * (alpha * 255)
    if overlay:
        img += 128
    img = img.clip(0,255).astype(np.ubyte)
    return img


def renderStack(overlay=True):  
    """
    Export label data as a 3D, RGB image
    if overlay is True, multiply in the original data image
    """
    stack = np.zeros(displayLabel.shape + (4,), dtype=np.ubyte)
    with pg.ProgressDialog("Rendering label stack...", maximum=displayLabel.shape[0]) as dlg:
        for z in range(displayLabel.shape[0]):
            stack[z] = renderLabels(z)
            if overlay:  ## multiply colors, not alpha.
                stack[z][..., :3] *= displayData[z].mean(axis=2)[..., np.newaxis].astype(float)/256.
            print(z)
        dlg += 1
        if dlg.wasCanceled():
            raise Exception("Stack render canceled.")
    return stack
    
def renderVolume(stack, alpha=0.3, loss=0.01):
    im = np.zeros(stack.shape[1:3]+(3,), dtype=float)                                                                                                
    for z in range(stack.shape[0]):                                                                                                       
        sz = stack[z].astype(float) # -128 
        mask = sz.max(axis=2) > 0
        szm = sz[mask]
        alphaChan = szm[...,3:4]*alpha/256.
        im *= (1.0-loss)
        im[mask] *= 1.0-alphaChan
        im[mask] += szm[...,:3] * alphaChan
        #im[mask] *= (1.0-alpha)
        #im[mask] += sz[mask] * alpha
        print(z)
    return im

def updateLabelImage(sl=None):
    global labelCache
    if labelCache is None:  ## if we haven't cached a full frame, then the full frame must be rendered.
        sl = (slice(None), slice(None))
    
    img = renderLabels(ui.zSlider.value(), sl, overlay=ui.overlayCheck.isChecked())
    
    if labelCache is None:
        labelCache = img
        labelImg.setImage(labelCache, levels=None)
    else:
        labelCache[sl] = img
        labelImg.updateImage()

    

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
    displayLabel = label.transpose(axes).view(np.ndarray)
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
