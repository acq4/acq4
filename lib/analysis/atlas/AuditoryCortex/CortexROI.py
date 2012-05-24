import pyqtgraph as pg
from pyqtgraph.graphicsItems import ROI

class CortexROI(ROI.PolyLineROI):
    
    def __init__(self, pos, state=None):
        ROI.PolyLineROI.__init__(self, [[0,0], [2,0], [2,1], [0,1]], size=(1e-3, 1e-3), pos=pos, closed=True)
        
        ## don't let the user add handles to the sides, only to the top and bottom
        self.segments[1].setAcceptsHandles(False)
        self.segments[3].setAcceptsHandles(False)
        
        self.pen = pg.mkPen(50,50, 255, 200)
        
        #self.layerLines = []
        #for i in range(4):
        #    self.layerLines.append(ROI.LineSegmentROI([[0, 0.2*(i+1)], [2, 0.2*(i+1)]], parent=self))
        
    def newHandleRequested(self, segment, ev): ## ev should be in this item's coordinate system
        
        pos = ev.pos()
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
        """Return a list of quadrilaterals (each a list of 4 points, in scene coordinates) formed by the ROI."""
        n = len(self.handles)
        quads = []
        positions = self.getSceneHandlePositions()
        for i in range(n/2-1):
            quad=[]
            quad.append(positions[i][1]) 
            quad.append(positions[i+1][1])
            quad.append(positions[-(i+2)][1])
            quad.append(positions[-(i+1)][1])
            quads.append(quad)
            
        return quads
            