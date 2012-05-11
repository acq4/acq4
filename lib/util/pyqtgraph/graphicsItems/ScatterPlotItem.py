from pyqtgraph.Qt import QtGui, QtCore
from pyqtgraph.Point import Point
import pyqtgraph.functions as fn
#from GraphicsItem import GraphicsItem
from GraphicsObject import GraphicsObject
import numpy as np
import scipy.stats
import weakref
import pyqtgraph.debug as debug
#import pyqtgraph as pg 

__all__ = ['ScatterPlotItem', 'SpotItem']


## Build all symbol paths
Symbols = {name: QtGui.QPainterPath() for name in ['o', 's', 't', 'd', '+']}

Symbols['o'].addEllipse(QtCore.QRectF(-0.5, -0.5, 1, 1))
Symbols['s'].addRect(QtCore.QRectF(-0.5, -0.5, 1, 1))
coords = {
    't': [(-0.5, -0.5), (0, 0.5), (0.5, -0.5)],
    'd': [(0., -0.5), (-0.4, 0.), (0, 0.5), (0.4, 0)],
    '+': [
        (-0.5, -0.05), (-0.5, 0.05), (-0.05, 0.05), (-0.05, 0.5),
        (0.05, 0.5), (0.05, 0.05), (0.5, 0.05), (0.5, -0.05), 
        (0.05, -0.05), (0.05, -0.5), (-0.05, -0.5), (-0.05, -0.05)
    ],
}
for k, c in coords.iteritems():
    Symbols[k].moveTo(*c[0])
    for x,y in c[1:]:
        Symbols[k].lineTo(x, y)
    Symbols[k].closeSubpath()



class ScatterPlotItem(GraphicsObject):
    """
    Displays a set of x/y points. Instances of this class are created
    automatically as part of PlotDataItem; these rarely need to be instantiated
    directly.
    
    The size, shape, pen, and fill brush may be set for each point individually 
    or for all points. 
    
    
    ========================  ===============================================
    **Signals:**
    sigPlotChanged(self)      Emitted when the data being plotted has changed
    sigClicked(self, points)  Emitted when the curve is clicked. Sends a list
                              of all the points under the mouse pointer.
    ========================  ===============================================
    
    """
    #sigPointClicked = QtCore.Signal(object, object)
    sigClicked = QtCore.Signal(object, object)  ## self, points
    sigPlotChanged = QtCore.Signal(object)
    
    def __init__(self, *args, **kargs):
        """
        Accepts the same arguments as setData()
        """
        prof = debug.Profiler('ScatterPlotItem.__init__', disabled=True)
        GraphicsObject.__init__(self)
        self.setFlag(self.ItemHasNoContents, True)
        self.data = None
        #self.spots = []
        #self.fragments = None
        self.bounds = [None, None]
        self.opts = {}
        self.spotsValid = False
        #self.itemsValid = False
        self._spotPixmap = None
        
        self.setPen(200,200,200, update=False)
        self.setBrush(100,100,150, update=False)
        self.setSymbol('o', update=False)
        self.setSize(7, update=False)
        self.setPxMode(True, update=False)
        #self.setIdentical(False, update=False)
        prof.mark('1')
        self.setData(*args, **kargs)
        prof.mark('setData')
        prof.finish()
        
    def setData(self, *args, **kargs):
        """
        **Ordered Arguments:**
        
        * If there is only one unnamed argument, it will be interpreted like the 'spots' argument.
        * If there are two unnamed arguments, they will be interpreted as sequences of x and y values.
        
        ====================== ===============================================================================================
        **Keyword Arguments:**
        *spots*                Optional list of dicts. Each dict specifies parameters for a single spot:
                               {'pos': (x,y), 'size', 'pen', 'brush', 'symbol'}. This is just an alternate method
                               of passing in data for the corresponding arguments.
        *x*,*y*                1D arrays of x,y values.
        *pos*                  2D structure of x,y pairs (such as Nx2 array or list of tuples)
        *pxMode*               If True, spots are always the same size regardless of scaling, and size is given in px.
                               Otherwise, size is in scene coordinates and the spots scale with the view.
                               Default is True
        *symbol*               can be one (or a list) of:
                               
                               * 'o'  circle (default)
                               * 's'  square
                               * 't'  triangle
                               * 'd'  diamond
                               * '+'  plus
        *pen*                  The pen (or list of pens) to use for drawing spot outlines.
        *brush*                The brush (or list of brushes) to use for filling spots.
        *size*                 The size (or list of sizes) of spots. If *pxMode* is True, this value is in pixels. Otherwise,
                               it is in the item's local coordinate system.
        *data*                 a list of python objects used to uniquely identify each spot.
        *identical*            *Deprecated*. This functionality is handled automatically now.
        ====================== ===============================================================================================
        """
        prof = debug.Profiler('ScatterPlotItem.setData', disabled=True)
        self.clear()  ## clear out all old data

        
        ## deal with non-keyword arguments
        if len(args) == 1:
            kargs['spots'] = args[0]
        elif len(args) == 2:
            kargs['x'] = args[0]
            kargs['y'] = args[1]
        elif len(args) > 2:
            raise Exception('Only accepts up to two non-keyword arguments.')
        
        ## convert 'pos' argument to 'x' and 'y'
        if 'pos' in kargs:
            pos = kargs['pos']
            if isinstance(pos, np.ndarray):
                kargs['x'] = pos[:,0]
                kargs['y'] = pos[:,1]
            else:
                x = []
                y = []
                for p in pos:
                    if isinstance(p, QtCore.QPointF):
                        x.append(p.x())
                        y.append(p.y())
                    else:
                        x.append(p[0])
                        y.append(p[1])
                kargs['x'] = x
                kargs['y'] = y
        prof.mark('1')
        ## determine how many spots we have
        if 'spots' in kargs:
            numPts = len(kargs['spots'])
        elif 'y' in kargs and kargs['y'] is not None:
            numPts = len(kargs['y'])
        else:
            kargs['x'] = []
            kargs['y'] = []
            numPts = 0
        
        prof.mark('2')
        ## create empty record array
        self.data = np.empty(numPts, dtype=[('x', float), ('y', float), ('size', float), ('symbol', 'S1'), ('pen', object), ('brush', object), ('spot', object), ('item', object), ('data', object)])
        #self.data['index'] = np.arange(numPts)
        self.data['size'] = -1  ## indicates to use default size
        
        ## This seems to be unnecessary--np.empty initializes these fields correctly on its own.
        #self.data['symbol'] = ''
        #self.data['pen'] = None
        #self.data['brush'] = None
        #self.data['data'] = None
        #self.data['item'] = None
        #self.data['spot'] = None
        
        prof.mark('3')
        if 'spots' in kargs:
            spots = kargs['spots']
            for i in xrange(len(spots)):
                spot = spots[i]
                for k in spot:
                    if k == 'pen':
                        self.data[i][k] = fn.mkPen(spot[k])
                    elif k == 'brush':
                        self.data[i][k] = fn.mkBrush(spot[k])
                    elif k == 'pos':
                        pos = spot[k]
                        if isinstance(pos, QtCore.QPointF):
                            x,y = pos.x(), pos.y()
                        else:
                            x,y = pos[0], pos[1]
                        self.data[i]['x'] = x
                        self.data[i]['y'] = y
                    elif k in ['x', 'y', 'size', 'symbol', 'data']:
                        self.data[i][k] = spot[k]
                    #elif k == 'data':
                        #self.pointData[i] = spot[k]
                    else:
                        raise Exception("Unknown spot parameter: %s" % k)
        elif 'y' in kargs:
            self.data['x'] = kargs['x']
            self.data['y'] = kargs['y']
        prof.mark('4')
        
        
        ## Set any extra parameters provided in keyword arguments
        for k in ['pxMode', 'pen', 'brush', 'symbol', 'size']:
            if k in kargs:
                setMethod = getattr(self, 'set' + k[0].upper() + k[1:])
                setMethod(kargs[k], update=False)
        
        if 'data' in kargs:
            self.setPointData(kargs['data'])
        prof.mark('5')
            
        #self.updateSpots()
        self.generateSpotItems()
        prof.mark('6')
        prof.finish()
        
    def setPoints(self, *args, **kargs):
        ##Deprecated; use setData
        return self.setData(*args, **kargs)
        
    def implements(self, interface=None):
        ints = ['plotData']
        if interface is None:
            return ints
        return interface in ints
    
    def setPen(self, *args, **kargs):
        """Set the pen(s) used to draw the outline around each spot. 
        If a list or array is provided, then the pen for each spot will be set separately.
        Otherwise, the arguments are passed to pg.mkPen and used as the default pen for 
        all spots which do not have a pen explicitly set."""
        if 'update' in kargs:
            update = kargs['update']
            del kargs['update']
        else:
            update = True
            
        if len(args) == 1 and (isinstance(args[0], np.ndarray) or isinstance(args[0], list)):
            pens = args[0]
            if self.data is None:
                raise Exception("Must set data before setting multiple pens.")
            if len(pens) != len(self.data):
                raise Exception("Number of pens does not match number of points (%d != %d)" % (len(pens), len(self.data)))
            for i in xrange(len(pens)):
                self.data[i]['pen'] = fn.mkPen(pens[i])
        else:
            self.opts['pen'] = fn.mkPen(*args, **kargs)
            self._spotPixmap = None
        
        if update:
            self.updateSpots()
        
    def setBrush(self, *args, **kargs):
        """Set the brush(es) used to fill the interior of each spot. 
        If a list or array is provided, then the brush for each spot will be set separately.
        Otherwise, the arguments are passed to pg.mkBrush and used as the default brush for 
        all spots which do not have a brush explicitly set."""
        if 'update' in kargs:
            update = kargs['update']
            del kargs['update']
        else:
            update = True
            
        if len(args) == 1 and (isinstance(args[0], np.ndarray) or isinstance(args[0], list)):
            brushes = args[0]
            if self.data is None:
                raise Exception("Must set data before setting multiple brushes.")
            if len(brushes) != len(self.data):
                raise Exception("Number of brushes does not match number of points (%d != %d)" % (len(brushes), len(self.data)))
            for i in xrange(len(brushes)):
                self.data[i]['brush'] = fn.mkBrush(brushes[i], **kargs)
        else:
            self.opts['brush'] = fn.mkBrush(*args, **kargs)
            self._spotPixmap = None
        
        if update:
            self.updateSpots()

    def setSymbol(self, symbol, update=True):
        """Set the symbol(s) used to draw each spot. 
        If a list or array is provided, then the symbol for each spot will be set separately.
        Otherwise, the argument will be used as the default symbol for 
        all spots which do not have a symbol explicitly set."""
        if isinstance(symbol, np.ndarray) or isinstance(symbol, list):
            symbols = symbol
            if self.data is None:
                raise Exception("Must set data before setting multiple symbols.")
            if len(symbols) != len(self.data):
                raise Exception("Number of symbols does not match number of points (%d != %d)" % (len(symbols), len(self.data)))
            self.data['symbol'] = symbols
        else:
            self.opts['symbol'] = symbol
            self._spotPixmap = None
        
        if update:
            self.updateSpots()
    
    def setSize(self, size, update=True):
        """Set the size(s) used to draw each spot. 
        If a list or array is provided, then the size for each spot will be set separately.
        Otherwise, the argument will be used as the default size for 
        all spots which do not have a size explicitly set."""
        if isinstance(size, np.ndarray) or isinstance(size, list):
            sizes = size
            if self.data is None:
                raise Exception("Must set data before setting multiple sizes.")
            if len(sizes) != len(self.data):
                raise Exception("Number of sizes does not match number of points (%d != %d)" % (len(sizes), len(self.data)))
            self.data['size'] = sizes
        else:
            self.opts['size'] = size
            self._spotPixmap = None
            
        if update:
            self.updateSpots()
        
    def setPointData(self, data):
        if isinstance(data, np.ndarray) or isinstance(data, list):
            if self.data is None:
                raise Exception("Must set xy data before setting meta data.")
            if len(data) != len(self.data):
                raise Exception("Length of meta data does not match number of points (%d != %d)" % (len(data), len(self.data)))
        #self.pointData = data
        self.data['data'] = data
        #self.updateSpots()
        
        
    #def setIdentical(self, ident, update=True):
        #self.opts['identical'] = ident
        
        #if update:
            #self.updateSpots()
        
    def setPxMode(self, mode, update=True):
        self.opts['pxMode'] = mode
        
        if update:
            self.updateSpots()
        
    def updateSpots(self):
        self.clearItems()
        #self.spotsValid = False
        #self.update()
        
        self.generateSpotItems()
        
    def clear(self):
        if self.data is None:
            return
            
        self.clearItems()
        #for i in self.data['item']:
            #i.setParentItem(None)
            #s = i.scene()
            #if s is not None:
                #s.removeItem(i)
        #self.spots = []
        self.data = None
        self.spotsValid = False
        #self.itemsValid = False
        self.bounds = [None, None]
        
    def clearItems(self):
        ## Remove all spot graphics items
        if self.data is None:
            return
            
        for i in self.data['item']:
            if i is None:
                continue
            #i.setParentItem(None)
            s = i.scene()
            if s is not None:
                s.removeItem(i)
        self.data['item'] = None

    def dataBounds(self, ax, frac=1.0, orthoRange=None):
        if frac >= 1.0 and self.bounds[ax] is not None:
            return self.bounds[ax]
        
        if self.data is None or len(self.data) == 0:
            return (None, None)
        
        if ax == 0:
            d = self.data['x']
            d2 = self.data['y']
        elif ax == 1:
            d = self.data['y']
            d2 = self.data['x']
        
        if orthoRange is not None:
            mask = (d2 >= orthoRange[0]) * (d2 <= orthoRange[1])
            d = d[mask]
            d2 = d2[mask]
            
        if frac >= 1.0:
            minIndex = np.argmin(d)
            maxIndex = np.argmax(d)
            minVal = d[minIndex]
            maxVal = d[maxIndex]
            if not self.opts['pxMode']:
                minVal -= self.data[minIndex]['size']
                maxVal += self.data[maxIndex]['size']
            self.bounds[ax] = (minVal, maxVal)
            return self.bounds[ax]
        elif frac <= 0.0:
            raise Exception("Value for parameter 'frac' must be > 0. (got %s)" % str(frac))
        else:
            return (scipy.stats.scoreatpercentile(d, 50 - (frac * 50)), scipy.stats.scoreatpercentile(d, 50 + (frac * 50)))
            
            

    
    def addPoints(self, *args, **kargs):
        """
        Add new points to the scatter plot. 
        Arguments are the same as setData()
        Note: this is expensive; plenty of room for optimization here.
        """
        if self.data is None:
            self.setData(*args, **kargs)
            return
            
        
        data1 = self.data[:]
        self.setData(*args, **kargs)
        newData = np.empty(len(self.data) + len(data1), dtype=self.data.dtype)
        newData[:len(data1)] = data1
        newData[len(data1):] = self.data
        self.data = newData
        #newData['index'] = np.arange(len(newData))
        self.sigPlotChanged.emit(self)
    
    
    def generateSpotItems(self):
        if self.data is None:
            return
            
        for rec in self.data:
            print "make:", rec['data']
            self.makeSpotItem(rec)
        
        self.sigPlotChanged.emit(self)

    #def paint(self, p, *args):
        #if not self.spotsValid:
            #self.generateSpots()
        #if self.fragments is not None:
            #pm = self.spotPixmap()
            #p.drawPixmapFragments(self.fragments, pm)

    def defaultSpotPixmap(self):
        ## Return the default spot pixmap
        if self._spotPixmap is None:
            self._spotPixmap = self.makeSpotImage(size=self.opts['size'], brush=self.opts['brush'], pen=self.opts['pen'], symbol=self.opts['symbol'])
        return self._spotPixmap

    def makeSpotImage(self, size, pen, brush, symbol=None):
        ## Render a spot with the given parameters to a pixmap
        image = QtGui.QImage(size+2, size+2, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        p = QtGui.QPainter(image)
        p.setRenderHint(p.Antialiasing)
        p.translate(size*0.5+1, size*0.5+1)
        p.scale(size, size)
        p.setPen(pen)
        p.setBrush(brush)
        p.drawPath(Symbols[symbol])
        p.end()
        return QtGui.QPixmap(image)
        
    def makeSpotItem(self, data):
        ## Create either a QGraphicsPixmapItem or QGraphicsPathItem
        ## for the given spot. (data must be a single item from self.data)
        if data['item'] is not None:
            return
            
        symbolOpts = (data['pen'], data['brush'], data['size'], data['symbol'])
        
        ## If in pxMode and all symbol options are default, use default pixmap
        if self.opts['pxMode'] and symbolOpts == (None, None, -1, ''):
            img = self.defaultSpotPixmap()
            item = self.makeSpotImageItem(img)
        else:
            ## Apply default options where appropriate
            pen, brush, size, symbol = symbolOpts
            if brush is None:
                brush = self.opts['brush']
            if pen is None:
                pen = self.opts['pen']
            if size == -1:
                size = self.opts['size']
            if symbol == '':
                symbol = self.opts['symbol']
            brush = fn.mkBrush(brush)
            pen = fn.mkPen(pen)
            try:
                n = int(symbol)
                symbol = Symbols.keys()[n % len(Symbols)]
            except:
                pass
            
            #defOpts = (self.opts['symbol'], self.opts['size'], self.opts['brush'], self.opts['pen'])
            if self.opts['pxMode']:
                pixmap = self.makeSpotImage(size, pen, brush, symbol)
                item = self.makeSpotImageItem(pixmap)
                #item = QtGui.QGraphicsPixmapItem()
                #item.setFlags(item.flags() | item.ItemIgnoresTransformations)
                #item.setOffset(-img.width()/2.+0.5, -img.height()/2.)
                ##item.setShapeMode(item.BoundingRectShape)
                #item.setPixmap(img)
                ##item = SpotItem(size, pxMode, brush, pen, data, symbol=symbol, image=img, index=index)
            else:
                item = self.makeSpotPathItem(symbol, size, pen, brush)
                #item = QtGui.QGraphicsPathItem(Symbols[symbol])
                #item.setPen(pen)
                #item.setBrush(brush)
                #item.scale(size, size)
                #item = SpotItem(size, pxMode, brush, pen, data, symbol=symbol, index=index)
        item.setParentItem(self)
        item.setPos(QtCore.QPointF(data['x'], data['y']))
        data['item'] = item
        #item.sigClicked.connect(self.pointClicked)
        return item
        
    def makeSpotImageItem(self, pixmap):
        ## Create a QGraphicsImageItem with the given pixmap
        item = QtGui.QGraphicsPixmapItem()
        item.setFlags(item.flags() | item.ItemIgnoresTransformations)
        item.setOffset(-pixmap.width()/2.+0.5, -pixmap.height()/2.)
        #item.setShapeMode(item.BoundingRectShape)
        item.setPixmap(pixmap)
        return item
        
    def makeSpotPathItem(self, symbol, size, pen, brush):
        ## Create a QGraphicsPathItem with the given properties
        item = QtGui.QGraphicsPathItem(Symbols[symbol])
        item.setPen(pen)
        item.setBrush(brush)
        item.scale(size, size)
        return item
        
    #def mkSpotItem(self, pos, size, pxMode, brush, pen, data, symbol=None):
        ### Make and return a SpotItem (or PixmapSpotItem if in pxMode)
        #brush = fn.mkBrush(brush)
        #pen = fn.mkPen(pen)
        #try:
            #n = int(symbol)
            #symbol = Symbols.keys()[n % len(Symbols)]
        #except:
            #pass
        
        #defOpts = (self.opts['symbol'], self.opts['size'], self.opts['brush'], self.opts['pen'])
        #if pxMode:
            ##if self.opts['identical']:
            #if (symbol, size, pen, brush) == defOpts:
                #print "use default image"
                #img = self.spotPixmap()
            #else:
                #img = self.makeSpotImage(size, pen, brush, symbol)
            #item = QtGui.QGraphicsPixmapItem()
            #item.setFlags(item.flags() | item.ItemIgnoresTransformations)
            #item.setOffset(-img.width()/2.+0.5, -img.height()/2.)
            ##item.setShapeMode(item.BoundingRectShape)
            #item.setPixmap(img)
            ##item = SpotItem(size, pxMode, brush, pen, data, symbol=symbol, image=img, index=index)
        #else:
            #item = QtGui.QGraphicsPathItem(Symbols[symbol])
            #item.setPen(pen)
            #item.setBrush(brush)
            #item.scale(size, size)
            ##item = SpotItem(size, pxMode, brush, pen, data, symbol=symbol, index=index)
        #item.setParentItem(self)
        #item.setPos(pos)
        ##item.sigClicked.connect(self.pointClicked)
        #return item
        
    def boundingRect(self):
        (xmn, xmx) = self.dataBounds(ax=0)
        (ymn, ymx) = self.dataBounds(ax=1)
        if xmn is None or xmx is None:
            xmn = 0
            xmx = 0
        if ymn is None or ymx is None:
            ymn = 0
            ymx = 0
        return QtCore.QRectF(xmn, ymn, xmx-xmn, ymx-ymn)
        
    def points(self):
        if not self.spotsValid:
            self.generateSpots()
        return self.data['spot']
        
    def generateSpots(self):
        for i in self.data:
            if i['spot'] is None:
                i['spot'] = Spot(i, self)

    def pointsAt(self, pos):
        x = pos.x()
        y = pos.y()
        pw = self.pixelWidth()
        ph = self.pixelHeight()
        pts = []
        for s in self.points():
            sp = s.pos()
            ss = s.size()
            sx = sp.x()
            sy = sp.y()
            s2x = s2y = ss * 0.5
            if self.opts['pxMode']:
                s2x *= pw
                s2y *= ph
            if x > sx-s2x and x < sx+s2x and y > sy-s2y and y < sy+s2y:
                pts.append(s)
                #print "HIT:", x, y, sx, sy, s2x, s2y
            #else:
                #print "No hit:", (x, y), (sx, sy)
                #print "       ", (sx-s2x, sy-s2y), (sx+s2x, sy+s2y)
        pts.sort(lambda a,b: cmp(b.zValue(), a.zValue()))
        return pts
            

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            pts = self.pointsAt(ev.pos())
            if len(pts) > 0:
                self.ptsClicked = pts
                self.sigClicked.emit(self, self.ptsClicked)
                ev.accept()
            else:
                #print "no spots"
                ev.ignore()
        else:
            ev.ignore()


class Spot:
    """
    Class referring to individual spots in a scatter plot.
    These can be retrieved by calling ScatterPlotItem.points() or 
    by connecting to the ScatterPlotItem's click signals.
    
    Note that this is *not* a GraphicsItem class; it is a data handling
    class. Use Spot.item() to access the GraphicsItem associated with this spot.
    """

    def __init__(self, data, plot):
        self._data = data
        self._plot = plot
        self._viewBox = None

    def pos(self):
        """Return the position of this spot."""
        return QtCore.QPointF(self._data['x'], self._data['y'])
        
    def viewPos(self):
        """Return the position of this spot in the coordinate system of its GraphicsItem's ViewBox."""
        vb = self.getViewBox()
        if vb is None:
            return None
        return vb.mapFromItemToView(self.item(), self.pos())
        
    def getViewBox(self):
        """Return the ViewBox which contains this spot's GraphicsItem"""
        if self._viewBox is None:
            p = self.item()
            while True:
                p = p.parentItem()
                if p is None:
                    return None
                if hasattr(p, 'implements') and p.implements('ViewBox'):
                    self._viewBox = weakref.ref(p)
                    break
        return self._viewBox()  ## If we made it this far, _viewBox is definitely not None
        
        
    def zValue(self):
        return self.item().zValue()

    def setZValue(self, z):
        return self.item().setZValue(z)

    def item(self):
        """Return the GraphicsItem displaying this spot."""
        return self._data['item']
        
    def data(self):
        """Return the user data associated with this spot."""
        return self._data['data']
        
    def size(self):
        """Return the size of this spot. 
        If the spot has no explicit size set, then return the ScatterPlotItem's default size instead."""
        if self._data['size'] == -1:
            return self._plot.opts['size']
        else:
            return self._data['size']
            
    def setSize(self, size):
        """Set the size of this spot. 
        If the size is set to -1, then the ScatterPlotItem's default size 
        will be used instead."""
        self._data['size'] = size
        self.updateItem()
        
    def symbol(self):
        """Return the symbol of this spot. 
        If the spot has no explicit symbol set, then return the ScatterPlotItem's default symbol instead."""
        if self._data['symbol'] == '':
            return self._plot.opts['size']
        else:
            return self._data['size']
        
    def setSymbol(self, symbol):
        """Set the symbol for this spot.
        If the symbol is set to '', then the ScatterPlotItem's default symbol will be used instead."""
        self._data['symbol'] = symbol
        self.updateItem()
        
    def setPen(self, *args, **kargs):
        """Set the outline pen for this spot"""
        pen = fn.mkPen(*args, **kargs)
        self._data['pen'] = pen
        self.updateItem()
        
    def setBrush(self, *args, **kargs):
        """Set the fill brush for this spot"""
        brush = fn.mkBrush(*args, **kargs)
        self._data['brush'] = brush
        self.updateItem()
        
    def resetBrush(self):
        """Remove the brush set for this spot; the scatter plot's default brush will be used instead."""
        self._data['brush'] = None  ## Note this is NOT the same as calling setBrush(None)
        self.updateItem()
        
    def resetPen(self):
        """Remove the pen set for this spot; the scatter plot's default pen will be used instead."""
        self._data['pen'] = None  ## Note this is NOT the same as calling setPen(None)
        self.updateItem()
        
    def setData(self, data):
        """Set the user-data associated with this spot"""
        self._data['data'] = data
        
    def updateItem(self):
        z = self.zValue()
        if self._data['item'] is not None:
            item = self._data['item']
            #item.setParent(None)
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._data['item'] = None
        self._plot.makeSpotItem(self._data)
        self.setZValue(z)
