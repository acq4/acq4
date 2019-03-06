from acq4.pyqtgraph.Qt import QtCore, QtGui
import acq4.pyqtgraph as pg
from CanvasItem import CanvasItem
from .itemtypes import registerItemType


class CortexMarkerCanvasItem(CanvasItem):
    _typeName = "CortexMarker"
    
    def __init__(self, points=None, **kwds):
        vr = kwds.pop('viewRect', None)
        if points is None:
            if vr is None:
                points = ((0, 0), (1, 1))
            else:
                p1 = vr.center()
                p2 = p1 + 0.2 * (vr.topRight()-p1)
                points = ((p1.x(), p1.y()), (p2.x(), p2.y()))
        #item = pg.graphicsItems.ROI.RulerROI(points)
        item = CortexMarkerROI(points)
        CanvasItem.__init__(self, item, **kwds)

registerItemType(CortexMarkerCanvasItem)

class CortexMarkerROI(pg.graphicsItems.ROI.LineSegmentROI):
    def paint(self, p, *args):
        pg.graphicsItems.ROI.LineSegmentROI.paint(self, p, *args)
        h1 = self.handles[0]['item'].pos()
        h2 = self.handles[1]['item'].pos()
        p1 = p.transform().map(h1)
        p2 = p.transform().map(h2)

        vec = pg.Point(h2) - pg.Point(h1)
        length = vec.length()
        angle = -vec.angle(pg.Point(0,-1)) ## changed to match how Alice measured angle in optoanalysis/new_test_ui.py
        self.angle = angle

        pvec = p2 - p1
        pvecT = pg.Point(pvec.y(), -pvec.x())
        pos = 0.5 * (p1 + p2) + pvecT * 40 / pvecT.length()

        p.resetTransform()

        txt = pg.functions.siFormat(length, suffix='m') + '\n%0.1f deg' % angle
        p.drawText(QtCore.QRectF(pos.x()-50, pos.y()-50, 100, 100), QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, txt)
        p.drawText(QtCore.QRectF(p1.x(), p1.y()-10, 20,20), "Pia")
        p.drawText(QtCore.QRectF(p2.x(), p2.y()+10, 50,50), "White Matter")

    def boundingRect(self):
        r = pg.graphicsItems.ROI.LineSegmentROI.boundingRect(self)
        pxl = self.pixelLength(pg.Point([1, 0]))
        if pxl is None:
            return r
        pxw = 50 * pxl
        return r.adjusted(-50, -50, 50, 50)

