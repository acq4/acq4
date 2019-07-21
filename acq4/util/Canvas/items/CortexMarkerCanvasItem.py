from __future__ import print_function
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
                #p1 = vr.center()
                #p2 = p1 + 0.2 * (vr.topRight()-p1)
                #points = ((p1.x(), p1.y()), (p2.x(), p2.y()))
                p = vr.center()
                d = vr.topRight()-vr.center()
                points = ((p.x(), p.y()+0.6*d.y()), (p.x(), p.y()-0.6*d.y()))
                #print('points:', points)

        item = CortexMarkerROI(points, movable=True)
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


class CortexMarkerROI(pg.graphicsItems.ROI.ROI):

    def __init__(self, points=None, layers=None, **kwargs):

        #size = (pg.Point(points[1])-pg.Point(points[0])).length()
        #print('size:', size)
        size = (1,1)
        points = [(0,0), (1,1)]
        pg.graphicsItems.ROI.ROI.__init__(self, points[0], size=size, **kwargs)
        

        if layers is None:
            self.layers = ['L1', 'L2/3', 'L4', 'L5', 'L6']
        else:
            self.layers = layers

        #points = [(0,0)]
        #for i in range(len(layers)):
        #    points.append((0,(i+1)*.01))
        self.addScaleHandle([1,0.5], [0.5, 0.5])
        self.piaHandle = self.addScaleRotateHandle([0.5, 0], [0.5, 1], name='pia')
        self.freeHandles = []
        for i in range(len(self.layers)-1):
            h = self.addFreeHandle((0.5, float(i+1)/len(self.layers)))
            self.freeHandles.append(h)
            #print("addFreeHandle:", (0.5, float(i+1)/len(layers)))
        self.wmHandle = self.addScaleRotateHandle([0.5, 1], [0.5, 0], name='wm')

        #self.handles[0]['item'].movePoint(pg.Point(points[0]))
        #self.handles[-1]['item'].movePoint(pg.Point(points[1]))
        #self.scale(0.001)
        #self.stateChanged(finish=True)

    def checkPointMove(self, handle, pos, modifiers):
        ### don't allow layer boundary handles to move above or below the adjacent layer boundary lines (ie L4 must be between L3 and L5)
        ## pos is in scene coordinates

        index = self.indexOfHandle(handle)

        ## if this is one of our scale handles allow it
        if index in [0,1,len(self.handles)-1]:
            return True

        top = self.handles[index+1]['item'].pos().y()
        bottom = self.handles[index-1]['item'].pos().y()

        if bottom < self.mapFromScene(pos).y() < top:
            return True

        return False


    def paint(self, p, opt, widget):
        # Note: don't use self.boundingRect here, because subclasses may need to redefine it.
        r = QtCore.QRectF(0, 0, self.state['size'][0], self.state['size'][1]).normalized()
        
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.currentPen)
        p.translate(r.left(), r.top())
        p.scale(r.width(), r.height())
        p.drawRect(0, 0, 1, 1)


        nHues = len(self.layers)*2+2

        for i, h in enumerate(self.handles):
            if h['type'] == 'f':
                p.setPen(pg.mkPen(pg.intColor((i-2)*2+1, hues=nHues), width=2))
                y2 = h['pos'].y()
                p.drawLine(QtCore.QPointF(0,y2), QtCore.QPointF(1,y2))

        positions = []
        for i, l in enumerate(self.layers):
            y = (self.handles[2+i]['pos'].y() - self.handles[1+i]['pos'].y())/2. + self.handles[1+i]['pos'].y()
            positions.append(p.transform().map(QtCore.QPointF(0.5, y)))
            
        p.resetTransform()

        for i, l in enumerate(self.layers):
            pos = positions[i]
            p.setPen(pg.mkPen(pg.intColor((i*2), hues=nHues)))
            p.drawText(QtCore.QRectF(pos.x()-50, pos.y()-50, 100, 100), QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, l)










# class CortexMarkerROI(pg.graphicsItems.ROI.LineSegmentROI):
#     def __init__(self, *args, **kwds):
#         pg.graphicsItems.ROI.LineSegmentROI.__init__(self, *args, **kwds)

#     def paint(self, p, *args):
#         pg.graphicsItems.ROI.LineSegmentROI.paint(self, p, *args)
#         h1 = self.handles[0]['item'].pos()
#         h2 = self.handles[1]['item'].pos()
#         p1 = p.transform().map(h1)
#         p2 = p.transform().map(h2)

#         vec = pg.Point(self.mapToParent(h2)) - pg.Point(self.mapToParent(h1))
#         length = vec.length()
#         angle = -vec.angle(pg.Point(0,-1)) ## changed to match how Alice measured angle in optoanalysis/new_test_ui.py
#         self.angle = angle

#         pvec = p2 - p1
#         pvecT = pg.Point(pvec.y(), -pvec.x())
#         pos = 0.5 * (p1 + p2) + pvecT * 40 / pvecT.length()

#         p.resetTransform()

#         txt = pg.functions.siFormat(length, suffix='m') + '\n%0.1f deg' % angle
       
#         r = QtCore.QRectF(pos.x()-20, pos.y()-20, 80, 30)
#         p.drawText(r, QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter, txt)
#         r1 = QtCore.QRectF(p1.x(), p1.y()-10, 20,10)
#         p.drawText(r1, "Pia")
#         r2 = QtCore.QRectF(p2.x(), p2.y()+10, 40,25)
#         p.drawText(r2, "White Matter")

#     def boundingRect(self):
#         r = pg.graphicsItems.ROI.LineSegmentROI.boundingRect(self)
#         #return r

#         ### try to adjust for the text boxes so we don't get rendering artifacts 
#         pxw = self.pixelLength(pg.Point([1, 0]))
#         pxh = self.pixelLength(pg.Point([0, 1]))
#         if pxw is None or pxh is None:
#             return r

#         xBuf = 80*pxw
#         yBuf = 80*pxh
#         return r.adjusted(-xBuf, -yBuf, xBuf, yBuf)



