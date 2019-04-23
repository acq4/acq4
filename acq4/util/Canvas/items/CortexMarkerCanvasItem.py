from acq4.pyqtgraph.Qt import QtCore, QtGui
import acq4.pyqtgraph as pg
from CanvasItem import CanvasItem
from .itemtypes import registerItemType
import ctypes


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

        item = CortexMarkerROI(points, movable=False)
        CanvasItem.__init__(self, item, **kwds)



    def saveState(self, relativeTo=None):
        state = CanvasItem.saveState(self, relativeTo)
        roi = self.graphicsItem()
        state['piaPos'] = tuple(pg.Point(roi.mapToParent(roi.listPoints()[0])))
        state['wmPos'] = tuple(pg.Point(roi.mapToParent(roi.listPoints()[1])))
        state['sliceAngle'] = roi.angle
        state['roiPos'] = tuple(pg.Point(roi.pos()))

        return state


    def restoreState(self, state):
        CanvasItem.restoreState(self, state)
        roi = self.graphicsItem()
        roi.setPos(pg.Point(state['roiPos']))
        roi.handles[0]['item'].setPos(roi.mapFromParent(pg.Point(state['piaPos'])))
        roi.handles[1]['item'].setPos(roi.mapFromParent(pg.Point(state['wmPos'])))

        ## tell roi to incorporate handle movements
        roi.movePoint(roi.handles[0]['item'], roi.handles[0]['item'].scenePos(), coords='scene')
        roi.movePoint(roi.handles[1]['item'], roi.handles[1]['item'].scenePos(), coords='scene')

    def showSelectBox(self):
        self.selectBox.hide()

registerItemType(CortexMarkerCanvasItem)

class CortexMarkerROI(pg.graphicsItems.ROI.LineSegmentROI):
    def __init__(self, *args, **kwds):
        pg.graphicsItems.ROI.LineSegmentROI.__init__(self, *args, **kwds)

    def paint(self, p, *args):
        pg.graphicsItems.ROI.LineSegmentROI.paint(self, p, *args)
        h1 = self.handles[0]['item'].pos()
        h2 = self.handles[1]['item'].pos()
        p1 = p.transform().map(h1)
        p2 = p.transform().map(h2)

        vec = pg.Point(self.mapToParent(h2)) - pg.Point(self.mapToParent(h1))
        length = vec.length()
        angle = -vec.angle(pg.Point(0,-1)) ## changed to match how Alice measured angle in optoanalysis/new_test_ui.py
        self.angle = angle

        pvec = p2 - p1
        pvecT = pg.Point(pvec.y(), -pvec.x())
        pos = 0.5 * (p1 + p2) + pvecT * 40 / pvecT.length()

        p.resetTransform()

        txt = pg.functions.siFormat(length, suffix='m') + '\n%0.1f deg' % angle
       
        r = QtCore.QRectF(pos.x()-20, pos.y()-20, 80, 30)
        p.drawText(r, QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, txt)
        r1 = QtCore.QRectF(p1.x(), p1.y()-10, 20,10)
        p.drawText(r1, "Pia")
        r2 = QtCore.QRectF(p2.x(), p2.y()+10, 40,25)
        p.drawText(r2, "White Matter")

    def boundingRect(self):
        r = pg.graphicsItems.ROI.LineSegmentROI.boundingRect(self)
        #return r

        ### try to adjust for the text boxes so we don't get rendering artifacts 
        pxw = self.pixelLength(pg.Point([1, 0]))
        pxh = self.pixelLength(pg.Point([0, 1]))
        if pxw is None or pxh is None:
            return r

        xBuf = 80*pxw
        yBuf = 80*pxh
        return r.adjusted(-xBuf, -yBuf, xBuf, yBuf)

