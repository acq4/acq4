from pyqtgraph import ROI, Point
from acq4.util import Qt


class PolygonROI(ROI):   
    def __init__(self, positions, pos=None, **args):
        if pos is None:
            pos = [0,0]
        ROI.__init__(self, pos, [1,1], **args)
        for p in positions:
            self.addFreeHandle(p)
        self.setZValue(1000)
            
    def listPoints(self):
        return [p['item'].pos() for p in self.handles]
            
    def paint(self, p, *args):
        p.setRenderHint(Qt.QPainter.RenderHint.Antialiasing)
        p.setPen(self.currentPen)
        for i in range(len(self.handles)):
            h1 = self.handles[i]['item'].pos()
            h2 = self.handles[i-1]['item'].pos()
            p.drawLine(h1, h2)
        
    def boundingRect(self):
        r = Qt.QRectF()
        for h in self.handles:
            r |= self.mapFromItem(h['item'], h['item'].boundingRect()).boundingRect()   ## |= gives the union of the two QRectFs
        return r
    
    def shape(self):
        p = Qt.QPainterPath()
        p.moveTo(self.handles[0]['item'].pos())
        for i in range(len(self.handles)):
            p.lineTo(self.handles[i]['item'].pos())
        return p
    
    def stateCopy(self):
        sc = {}
        sc['pos'] = Point(self.state['pos'])
        sc['size'] = Point(self.state['size'])
        sc['angle'] = self.state['angle']
        return sc
