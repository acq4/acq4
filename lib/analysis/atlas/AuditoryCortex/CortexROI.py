import pyqtgraph as pg
from pyqtgraph.graphicsItems import ROI
from pyqtgraph.Point import Point
from PyQt4 import QtGui, QtCore
import math


class CortexROI(ROI.PolyLineROI):
    
    def __init__(self, pos, state=None):
        ROI.PolyLineROI.__init__(self, [[0,0], [2,0], [2,1], [0,1]], size=(1e-3, 1e-3), pos=pos, closed=True)
        
        ## don't let the user add handles to the sides, only to the top and bottom
        self.segments[1].setAcceptsHandles(False)
        self.segments[3].setAcceptsHandles(False)
        
        self.pen = pg.mkPen(50,50, 255, 200)
        
        if state is not None:
            self.setState(state)
        #self.layerLines = []
        #for i in range(4):
        #    self.layerLines.append(ROI.LineSegmentROI([[0, 0.2*(i+1)], [2, 0.2*(i+1)]], parent=self))
    def setState(self, state):
        ROI.PolyLineROI.setState(self, state)
        handles = state['handles']
        n = len(handles)
        
        ## set positions of 4 corners
        self.handles[0]['item'].setPos(self.mapFromParent(QtCore.QPointF(*handles[0])))
        self.handles[1]['item'].setPos(self.mapFromParent(QtCore.QPointF(*handles[n/2-1])))
        self.handles[2]['item'].setPos(self.mapFromParent(QtCore.QPointF(*handles[n/2])))
        self.handles[3]['item'].setPos(self.mapFromParent(QtCore.QPointF(*handles[-1])))
        
        for i in range(1, n/2-1):
            self.newHandleRequested(self.segments[i-1], pos=self.mapFromParent(QtCore.QPointF(*handles[i])))
        
        for i, h in enumerate(self.handles):
            h['item'].setPos(self.mapFromParent(QtCore.QPointF(*handles[i])))
            
        
    def newHandleRequested(self, segment, ev=None, pos=None): ## ev/pos should be in this item's coordinate system
        if ev != None:
            pos = ev.pos()
        elif pos != None:
            pos = pos
        else:
            raise Exception("Either an event or a position must be specified")
        
        ## figure out which segment to add corresponding handle to
        n = len(self.segments)
        ind = self.segments.index(segment)
        if ind >= n/2 and ind != n-1:
            mirrorInd = n/2-(2+ind-n/2)
        elif ind < n/2-1:
            mirrorInd = n/2-1+(n/2-1-ind)
        else:
            raise Exception("Handles cannot be added to segment %i" %ind)    
        
        ## figure out position at which to add second handle:
        h1 = pg.Point(self.mapFromItem(segment, segment.handles[0]['item'].pos()))
        h2 = pg.Point(self.mapFromItem(segment, segment.handles[1]['item'].pos()))
        
        dist = (h1-pos).length()/(h1-h2).length()
        
        h3 = pg.Point(self.mapFromItem(self.segments[mirrorInd], self.segments[mirrorInd].handles[0]['item'].pos()))
        h4 = pg.Point(self.mapFromItem(self.segments[mirrorInd], self.segments[mirrorInd].handles[1]['item'].pos()))
        
        mirrorPos = h4 - (h4-h3)*dist
        
        ## add handles:
        if mirrorInd > ind:
            ROI.PolyLineROI.newHandleRequested(self, self.segments[mirrorInd], pos=mirrorPos)
            ROI.PolyLineROI.newHandleRequested(self, segment, pos=pos)
            
            ROI.LineSegmentROI([pos, mirrorPos], [0,0], handles=(self.segments[ind].handles[1]['item'], self.segments[mirrorInd+1].handles[1]['item']), pen=pg.mkPen(50,50,255,100), movable=False, acceptsHandles=False, parent=self)
            
        else:
            ROI.PolyLineROI.newHandleRequested(self, segment, pos=pos)            
            ROI.PolyLineROI.newHandleRequested(self, self.segments[mirrorInd], pos=mirrorPos)
            ROI.LineSegmentROI([mirrorPos, pos], [0,0], handles=(self.segments[mirrorInd].handles[1]['item'], self.segments[ind+1].handles[1]['item']), pen=pg.mkPen(50,50,255,100), movable=False, acceptsHandles=False, parent=self)
        
        
    def getQuadrilaterals(self):
        """Return a list of quadrilaterals (each a list of 4 points, in self.parentItem coordinates) formed by the ROI."""
        n = len(self.handles)
        quads = []
        positions = self.getHandlePositions()
        for i in range(n/2-1):
            quad=[]
            quad.append(positions[i]) 
            quad.append(positions[i+1])
            quad.append(positions[-(i+2)])
            quad.append(positions[-(i+1)])
            quads.append(quad)
            
        return quads
    
    def getNormalizedRects(self):
        """Return a list of rectangles (each a list of 4 points, in self.parentItem coordinates) for quadrilaterals to be mapped into."""
        quads = self.getQuadrilaterals()
        widths = []
        for i, q in enumerate(quads):
            w = abs(Point((q[0]+(q[3]-q[0])/2.)-(q[1]+(q[2]-q[1])/2.)).length())
            widths.append(w)
            if QtGui.QPolygonF(q).containsPoint(QtCore.QPointF(0., 0.0002), QtCore.Qt.OddEvenFill):
                ind = i
        mids = (quads[ind][0]+(quads[ind][3]-quads[ind][0])/2.),(quads[ind][1]+(quads[ind][2]-quads[ind][1])/2.)
        xPos = -(Point(mids[0]).length()*math.sin(Point(mids[0]).angle(Point(0,1)))*(math.pi/180.))
        rects = []
        for i, q in enumerate(quads):
            rect = []
            if i < ind:
                rect.append([-sum(widths[i:ind])+xPos, 0.])
            elif i == ind:
                rect.append([xPos, 0.])
            elif i > ind:
                rect.append([sum(widths[ind:i])-xPos, 0.])
            rect.append([rect[0][0] + widths[i], 0.])
            rect.append([rect[0][0] + widths[i], 0.001])
            rect.append([rect[0][0], 0.001])
            rects.append(rect)
        return rects
    
                            
        
        
    def getHandlePositions(self):
        """Return a list handle positions in self.parentItem's coordinates. These are the coordinates that are marked by the grid."""
        positions = []
        for h in self.handles:
            positions.append(self.mapToParent(h['item'].pos()))       
        return positions 
            
    def saveState(self):
        state = ROI.PolyLineROI.saveState(self)
        state['handles'] = [(p.x(), p.y()) for p in self.getHandlePositions()]
        return state