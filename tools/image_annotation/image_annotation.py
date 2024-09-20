import os
import sys

import numpy as np

import pyqtgraph as pg
from MetaArray import MetaArray
from acq4.util import Qt

Ui_Form = Qt.loadUiType(os.path.join(os.path.dirname(__file__), 'imageAnnotation.ui'))[0]

if callable(getattr(Qt.QApplication, "setGraphicsSystem", None)):
    Qt.QApplication.setGraphicsSystem('raster')
label_cache = None


def main(filename):
    pg.mkQApp()

    win = Qt.QMainWindow()
    cw = Qt.QWidget()
    win.setCentralWidget(cw)
    ui = Ui_Form()
    ui.setupUi(cw)
    win.show()
    win.resize(800, 600)

    ui.labelTree.header().setSectionResizeMode(Qt.QHeaderView.ResizeToContents)

    win.setWindowTitle(f"Annotations: {filename}")
    base_name = os.path.splitext(filename)[0]
    label_file = f'{base_name}.labels.ma'

    data = MetaArray(file=filename, mmap=True)
    if not os.path.exists(label_file):
        label = MetaArray(np.zeros(data.shape, dtype=np.uint16), info=data.infoCopy()[:3] + [{'labels': {}}])
        label.write(label_file, mappable=True)
    label = MetaArray(file=label_file, mmap=True, writable=True)

    labelInfo = {}

    vb = pg.ViewBox()
    ui.view.setCentralItem(vb)
    vb.setAspectLocked(True)
    vb.invertY(False)
    hist = pg.HistogramLUTWidget(gradientPosition="left")
    ui.imgLayout.addWidget(hist, 0, 1)

    dataImg = pg.ImageItem()
    labelImg = pg.ImageItem()  # mode=Qt.QPainter.CompositionMode_Plus)
    # labelImg.setCompositionMode(Qt.QPainter.CompositionMode_Overlay)
    labelImg.setZValue(10)
    labelImg.setOpacity(1)
    vb.addItem(dataImg)
    vb.addItem(labelImg)

    ui.helpText.setHtml("""<dl>
        <dt>Mouse:</dt>
        <dd>Left-click and drag to draw</dd>
        <dd>Shift-click and drag to erase</dd>
        <dt>Right/Left:</dt>
        <dd>switch to next/prev frame</dd>
        <dt>Ctrl+Right/Left:</dt>
        <dd>switch to next/prev frame, also copying label</dd>
        <dt>Up/Down:</dt>
        <dd>increase/decrease label number</dd>
        <dt>Plus/Minus:</dt>
        <dd>increase/decrease radius</dd>
        <dt>Space:</dt>
        <dd>toggle label display</dd>
        <dt>g:</dt>
        <dd>toggle greyscale</dd>
    </dl>""")

    def connectSignals():
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
        for k in sorted(d.keys()):
            addLabel(d[k])

    def keyPressEvent(ev):
        k = ev.key()
        mod = ev.modifiers()
        if k == Qt.Qt.Key_Right:
            if mod & Qt.Qt.ControlModifier:
                copyLabel(1)
            ui.zSlider.setValue(ui.zSlider.value() + 1)
        elif k == Qt.Qt.Key_Left:
            if mod & Qt.Qt.ControlModifier:
                copyLabel(-1)
            ui.zSlider.setValue(ui.zSlider.value() - 1)
        elif k == Qt.Qt.Key_Up:
            ui.labelSpin.setValue(ui.labelSpin.value() + 1)
        elif k == Qt.Qt.Key_Down:
            ui.labelSpin.setValue(ui.labelSpin.value() - 1)
        elif k == Qt.Qt.Key_Plus:
            ui.radiusSpin.setValue(ui.radiusSpin.value() + 1)
        elif k == Qt.Qt.Key_Minus:
            ui.radiusSpin.setValue(ui.radiusSpin.value() - 1)
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

    def draw(src, dst, mask, srcSlice, dstSlice, ev):
        addLabel()

        # p = debug.Profiler('draw', disabled=True)
        label_frame = label[ui.zSlider.value()]
        # p.mark('1')
        mod = ev.modifiers()
        # mask = mask[srcSlice]
        src = src[srcSlice].astype(label_frame.dtype)
        if mod & Qt.Qt.ShiftModifier:
            # src = 1 - src
            label_frame[dstSlice] &= ~(src * 2 ** ui.labelSpin.value())
        # label_frame[dstSlice] = label_frame[dstSlice] * (1 - mask) + src * mask
        # p.mark('2')
        else:
            label_frame[dstSlice] |= src * 2 ** ui.labelSpin.value()
        # p.mark('3')
        updateLabelImage(dstSlice)
        # p.mark('4')
        # p.finish()

    def addLabel(info=None):
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
            info['color'] = pg.mkColor(f"#{info['color']}")

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
            meta.append({
                'id': k,
                'name': str(v['item'].text(1)),
                'color': pg.colorStr(v['btn'].color()),
                'visible': v['item'].checkState(0) == Qt.Qt.Checked
            })
        label._info[-1]['labels'] = meta
        label.writeMeta(label_file)

    def write_cellpose_masks():
        from cellpose.gui.gui import MainW
        parent: MainW = None
        flow_threshold, cellprob_threshold = parent.get_thresholds()
        dat = {
            "outlines":
                parent.outpix,
            "colors":
                parent.cellcolors[1:],
            "masks":
                parent.cellpix,
            "current_channel": (parent.color - 2) % 5,
            "filename":
                parent.filename,
            "flows":
                parent.flows,
            "zdraw":
                parent.zdraw,
            "model_path": 0,
            "flow_threshold":
                flow_threshold,
            "cellprob_threshold":
                cellprob_threshold,
            "normalize_params":
                parent.get_normalize_params(),
            "restore":
                parent.restore,
            "ratio":
                parent.ratio,
            "diameter": 35,
        }
        if parent.restore is not None:
            dat["img_restore"] = parent.stack_filtered
        np.save(f"{base_name}_seg.npy", dat)

    def itemSelected(item):
        ui.labelTree.editItem(item, 1)

    def copyLabel(n):
        i1 = ui.zSlider.value()
        i2 = i1 + n
        if i2 < 0 or i2 > label.shape[0]:
            return
        # label[i2] &= ~mask
        # label[i2] |= label[i1] & mask
        mask = np.uint16(2 ** ui.labelSpin.value())

        label[i2] = (label[i1] & mask) | (label[i2] & ~mask)

    def updateImage():
        currentPos[zAxis] = ui.zSlider.value()
        if ui.greyCheck.isChecked():
            img = data.view(np.ndarray)[ui.zSlider.value()].mean(axis=2)
        else:
            img = data.view(np.ndarray)[ui.zSlider.value()]
        dataImg.setImage(img, autoLevels=False)
        if labelImg.isVisible():
            updateLabelImage()

    def renderLabels(z, sl=None, overlay=False):
        # p = debug.Profiler('updateLabelImage', disabled=True)
        if sl is None:
            sl = (slice(None), slice(None))

        l = label.view(np.ndarray)[z]
        # p.mark('1')
        lsl = l[sl]
        img = np.empty(lsl.shape + (4,), dtype=float)

        # img.fill(128)
        img.fill(0)
        val = ui.labelSlider.value() / 128.

        for k, v in labelInfo.items():
            if v['item'].checkState(0) != Qt.Qt.Checked:
                continue
            c = pg.colorTuple(v['btn'].color())
            mask = (lsl & (2 ** k) > 0)
            alpha = c[3] / 255. * val
            img[mask] *= 1.0 - alpha
            img[..., 0] += mask * int(c[0] * alpha)
            img[..., 1] += mask * int(c[1] * alpha)
            img[..., 2] += mask * int(c[2] * alpha)
            # img[...,0] += mask * int(c[0] * val)
            # img[...,1] += mask * int(c[1] * val)
            # img[...,2] += mask * int(c[2] * val)
            img[..., 3] += mask * (alpha * 255)
        if overlay:
            img += 128
        img = img.clip(0, 255).astype(np.ubyte)
        return img

    def renderStack(overlay=True):
        """
        Export label data as a 3D, RGB image
        if overlay is True, multiply in the original data image
        """
        stack = np.zeros(label.shape + (4,), dtype=np.ubyte)
        with pg.ProgressDialog("Rendering label stack...", maximum=label.shape[0]) as dlg:
            for z in range(label.shape[0]):
                stack[z] = renderLabels(z)
                if overlay:  # multiply colors, not alpha.
                    stack[z][..., :3] *= data[z].mean(axis=2)[..., np.newaxis].astype(float) / 256.
                print(z)
            dlg += 1
            if dlg.wasCanceled():
                raise Exception("Stack render canceled.")
        return stack

    def renderVolume(stack, alpha=0.3, loss=0.01):
        im = np.zeros(stack.shape[1:3] + (3,), dtype=float)
        for z in range(stack.shape[0]):
            sz = stack[z].astype(float)  # -128
            mask = sz.max(axis=2) > 0
            szm = sz[mask]
            alphaChan = szm[..., 3:4] * alpha / 256.
            im *= (1.0 - loss)
            im[mask] *= 1.0 - alphaChan
            im[mask] += szm[..., :3] * alphaChan
            # im[mask] *= (1.0-alpha)
            # im[mask] += sz[mask] * alpha
            print(z)
        return im

    def updateLabelImage(sl=None):
        global label_cache
        if label_cache is None:  # if we haven't cached a full frame, then the full frame must be rendered.
            sl = (slice(None), slice(None))

        img = renderLabels(ui.zSlider.value(), sl, overlay=ui.overlayCheck.isChecked())

        if label_cache is None:
            label_cache = img
            labelImg.setImage(label_cache, levels=None)
        else:
            label_cache[sl] = img
            labelImg.updateImage()

    def imageChanged():
        global label_cache
        label_cache = None
        zAxis = 0

        # displayData = data.transpose(axes)
        # displayLabel = label.transpose(axes).view(np.ndarray)
        ui.zSlider.setMaximum(data.shape[0] - 1)
        ui.zSlider.setValue(currentPos[zAxis])

        updateImage()
        # vb.setRange(dataImg.boundingRect())
        vb.autoRange()

    def updateKernel():
        r = ui.radiusSpin.value() + 1
        d = (r * 2) - 1
        x = np.array([range(d)])
        y = x.transpose()
        drawKernel = (np.sqrt((x - r + 1) ** 2 + (y - r + 1) ** 2) < r - 1).astype(np.ubyte)
        labelImg.setDrawKernel(drawKernel, mask=drawKernel, center=(r - 1, r - 1), mode=draw)

    cw.keyPressEvent = keyPressEvent

    currentPos = [0, 0, 0]
    zAxis = 0

    init()
    imageChanged()
    hist.setImageItem(dataImg)
    pg.exec()


if __name__ == '__main__':
    main(sys.argv[1])
