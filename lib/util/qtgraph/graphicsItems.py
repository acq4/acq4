# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from numpy import *
import scipy.weave as weave
from scipy.weave import converters
from scipy.fftpack import fft
from lib.util.MetaArray import MetaArray
from lib.util.debug import *
from Point import *
from functions import *
import types, sys, struct


class ItemGroup(QtGui.QGraphicsItem):
    def boundingRect(self):
        return QtCore.QRectF()
        
    def paint(self, *args):
        pass
    
    def addItem(self, item):
        item.setParentItem(self)

## Multiple inheritance not allowed in PyQt. Retarded workaround:
class QObjectWorkaround:
    def __init__(self):
        self._qObj_ = QtCore.QObject()
    #def __getattr__(self, attr):
        #if attr == '_qObj_':
            #raise Exception("QObjectWorkaround not initialized!")
        #return getattr(self._qObj_, attr)
    def connect(self, *args):
        return QtCore.QObject.connect(self._qObj_, *args)
    def emit(self, *args):
        return QtCore.QObject.emit(self._qObj_, *args)


class ImageItem(QtGui.QGraphicsPixmapItem):
    def __init__(self, image=None, copy=True, *args):
        self.qimage = QtGui.QImage()
        self.pixmap = None
        self.useWeave = True
        self.blackLevel = None
        self.whiteLevel = None
        self.alpha = 1.0
        self.image = None
        self.clipLevel = None
        QtGui.QGraphicsPixmapItem.__init__(self, *args)
        #self.pixmapItem = QtGui.QGraphicsPixmapItem(self)
        if image is not None:
            self.updateImage(image, copy, autoRange=True)
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
    def setAlpha(self, alpha):
        self.alpha = alpha
        self.updateImage()
        
    #def boundingRect(self):
        #return self.pixmapItem.boundingRect()
        #return QtCore.QRectF(0, 0, self.qimage.width(), self.qimage.height())
        
    def width(self):
        if self.pixmap is None:
            return None
        return self.pixmap.width()
        
    def height(self):
        if self.pixmap is None:
            return None
        return self.pixmap.height()
        
    def setClipLevel(self, level=None):
        self.clipLevel = level
        
    #def paint(self, p, opt, widget):
        #pass
        #if self.pixmap is not None:
            #p.drawPixmap(0, 0, self.pixmap)
            #print "paint"

    def setLevels(self, white=None, black=None):
        if white is not None:
            self.whiteLevel = white
        if black is not None:
            self.blackLevel = black  
        self.updateImage()

    def updateImage(self, image=None, copy=True, autoRange=False, clipMask=None, white=None, black=None):
        axh = {'x': 0, 'y': 1, 'c': 2}
        #print "Update image", black, white
        if white is not None:
            self.whiteLevel = white
        if black is not None:
            self.blackLevel = black  
        
        
        if image is None:
            if self.image is None:
                return
        else:
            if copy:
                self.image = image.copy()
            else:
                self.image = image
        #print "  image max:", self.image.max(), "min:", self.image.min()
        
        # Determine scale factors
        if autoRange or self.blackLevel is None:
            self.blackLevel = self.image.min()
            self.whiteLevel = self.image.max()
        
        if self.blackLevel != self.whiteLevel:
            scale = 255. / (self.whiteLevel - self.blackLevel)
        else:
            scale = 0.
        
        
        ## Recolor and convert to 8 bit per channel
        # Try using weave, then fall back to python
        shape = self.image.shape
        black = float(self.blackLevel)
        try:
            if not self.useWeave:
                raise Exception('Skipping weave compile')
            sim = ascontiguousarray(self.image)
            sim.shape = sim.size
            im = zeros(sim.shape, dtype=ubyte)
            n = im.size
            
            code = """
            for( int i=0; i<n; i++ ) {
                float a = (sim(i)-black) * (float)scale;
                if( a > 255.0 )
                a = 255.0;
                else if( a < 0.0 )
                a = 0.0;
                im(i) = a;
            }
            """
            
            weave.inline(code, ['sim', 'im', 'n', 'black', 'scale'], type_converters=converters.blitz, compiler = 'gcc')
            sim.shape = shape
            im.shape = shape
        except:
            if self.useWeave:
                self.useWeave = False
                printExc("Weave compile failed, falling back to slower version. Error was:")
            self.image.shape = shape
            im = ((self.image - black) * scale).clip(0.,255.).astype(ubyte)
                

        try:
            im1 = empty((im.shape[axh['y']], im.shape[axh['x']], 4), dtype=ubyte)
        except:
            print im.shape, axh
            raise
        alpha = clip(int(255 * self.alpha), 0, 255)
        # Fill image 
        if im.ndim == 2:
            im2 = im.transpose(axh['y'], axh['x'])
            im1[..., 0] = im2
            im1[..., 1] = im2
            im1[..., 2] = im2
            im1[..., 3] = alpha
        elif im.ndim == 3:
            im2 = im.transpose(axh['y'], axh['x'], axh['c'])
            
            for i in range(0, im.shape[axh['c']]):
                im1[..., i] = im2[..., i]
            for i in range(im.shape[axh['c']], 4):
                im1[..., i] = alpha
        else:
            raise Exception("Image must be 2 or 3 dimensions")
        #self.im1 = im1
        # Display image
        
        if self.clipLevel is not None or clipMask is not None:
                if clipMask is not None:
                        mask = clipMask.transpose()
                else:
                        mask = (self.image < self.clipLevel).transpose()
                im1[..., 0][mask] *= 0.5
                im1[..., 1][mask] *= 0.5
                im1[..., 2][mask] = 255
        
        self.ims = im1.tostring()  ## Must be held in memory here because qImage won't do it for us :(
        qimage = QtGui.QImage(self.ims, im1.shape[1], im1.shape[0], QtGui.QImage.Format_ARGB32)
        self.pixmap = QtGui.QPixmap.fromImage(qimage)
        ##del self.ims
        self.setPixmap(self.pixmap)
        self.update()
        
    def getPixmap(self):
        return self.pixmap.copy()

class LabelItem(QtGui.QGraphicsWidget):
    def __init__(self, text, parent=None, **args):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.item = QtGui.QGraphicsTextItem(self)
        self.opts = args
        if 'color' not in args:
            self.opts['color'] = 'CCC'
        self.sizeHint = {}
        self.setText(text)
        
            
    def setAttr(self, attr, value):
        """Set default text properties. See setText() for accepted parameters."""
        self.opts[attr] = value
        
    def setText(self, text, **args):
        """Set the text and text properties in the label. Accepts optional arguments for auto-generating
        a CSS style string:
           color:   string (example: 'CCFF00')
           size:    string (example: '8pt')
           bold:    boolean
           italic:  boolean
           """
        self.text = text
        opts = self.opts.copy()
        for k in args:
            opts[k] = args[k]
        
        optlist = []
        if 'color' in opts:
            optlist.append('color: #' + opts['color'])
        if 'size' in opts:
            optlist.append('font-size: ' + opts['size'])
        if 'bold' in opts and opts['bold'] in [True, False]:
            optlist.append('font-weight: ' + {True:'bold', False:'normal'}[opts['bold']])
        if 'italic' in opts and opts['italic'] in [True, False]:
            optlist.append('font-style: ' + {True:'italic', False:'normal'}[opts['italic']])
        full = "<span style='%s'>%s</span>" % ('; '.join(optlist), text)
        #print full
        self.item.setHtml(full)
        self.updateMin()
        
    def resizeEvent(self, ev):
        c1 = self.boundingRect().center()
        c2 = self.item.mapToParent(self.item.boundingRect().center()) # + self.item.pos()
        dif = c1 - c2
        self.item.moveBy(dif.x(), dif.y())
        #print c1, c2, dif, self.item.pos()
        
    def setAngle(self, angle):
        self.angle = angle
        self.item.resetMatrix()
        self.item.rotate(angle)
        self.updateMin()
        
    def updateMin(self):
        bounds = self.item.mapRectToParent(self.item.boundingRect())
        self.setMinimumWidth(bounds.width())
        self.setMinimumHeight(bounds.height())
        #print self.text, bounds.width(), bounds.height()
        
        #self.sizeHint = {
            #QtCore.Qt.MinimumSize: (bounds.width(), bounds.height()),
            #QtCore.Qt.PreferredSize: (bounds.width(), bounds.height()),
            #QtCore.Qt.MaximumSize: (bounds.width()*2, bounds.height()*2),
            #QtCore.Qt.MinimumDescent: (0, 0)  ##?? what is this?
        #}
            
        
    #def sizeHint(self, hint, constraint):
        #return self.sizeHint[hint]
        
        

class PlotCurveItem(QtGui.QGraphicsWidget):
    """Class representing a single plot curve."""
    def __init__(self, y=None, x=None, copy=False, pen=None, shadow=None, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.xData = None  ## raw values
        self.yData = None
        self.xDisp = None  ## display values (after log / fft)
        self.yDisp = None
        
        
        self.path = None
        #self.dispPath = None
        
        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(200, 200, 200))
        self.pen = pen
        
        self.shadow = shadow
        if y is not None:
            self.updateData(y, x, copy)
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
        self.metaDict = {}
        self.opts = {
            'spectrumMode': False,
            'logMode': [False, False],
            'pointMode': False,
            'pointStyle': None,
            'decimation': False,
            'alphaHint': 1.0,
            'alphaMode': False
        }
            
        #self.fps = None
        
    def getData(self):
        if self.xData is None:
            return (None, None)
        if self.xDisp is None:
            x = self.xData
            y = self.yData
            if self.opts['spectrumMode']:
                f = fft(y) / len(y)
                y = abs(f[1:len(f)/2])
                dt = x[-1] - x[0]
                x = linspace(0, 0.5*len(x)/dt, len(y))
            if self.opts['logMode'][0]:
                x = log10(x)
            if self.opts['logMode'][1]:
                y = log10(y)
            self.xDisp = x
            self.yDisp = y
        #print self.yDisp.shape, self.yDisp.min(), self.yDisp.max()
        #print self.xDisp.shape, self.xDisp.min(), self.xDisp.max()
        return self.xDisp, self.yDisp
            
    #def generateSpecData(self):
        #f = fft(self.yData) / len(self.yData)
        #self.ySpec = abs(f[1:len(f)/2])
        #dt = self.xData[-1] - self.xData[0]
        #self.xSpec = linspace(0, 0.5*len(self.xData)/dt, len(self.ySpec))
        
    def getRange(self, ax, frac=1.0):
        (x, y) = self.getData()
        if x is None:
            return (0, 1)
        if ax == 0:
            return (x.min(), x.max())
        if ax == 1:
            return (y.min(), y.max())
        
    def setMeta(self, data):
        self.metaData = data
        
    def meta(self):
        return self.metaData
        
    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setColor(self, color):
        self.pen.setColor(color)
        self.update()
        
    def setAlpha(self, alpha, auto):
        self.opts['alphaHint'] = alpha
        self.opts['alphaMode'] = auto
        self.update()
        
    def setSpectrumMode(self, mode):
        self.opts['spectrumMode'] = mode
        self.xDisp = self.yDisp = None
        self.path = None
        self.update()
    
    def setLogMode(self, mode):
        self.opts['logMode'] = mode
        self.xDisp = self.yDisp = None
        self.path = None
        self.update()
    
    def setPointMode(self, mode):
        self.opts['pointMode'] = mode
        self.update()
        
    def setShadowPen(self, pen):
        self.shadow = pen
        self.update()

    def setData(self, x, y, copy=False):
        """For Qwt compatibility"""
        self.updateData(y, x, copy)
        
    def updateData(self, data, x=None, copy=False):
        if isinstance(data, list):
            data = array(data)
        if isinstance(x, list):
            x = array(x)
        if not isinstance(data, ndarray) or data.ndim > 2:
            raise Exception("Plot data must be 1 or 2D ndarray or MetaArray (data shape is %s)" % str(data.shape))
        if data.ndim == 2:  ### If data is 2D array, then assume x and y values are in first two columns or rows.
            if x is not None:
                raise Exception("Plot data may be 2D only if no x argument is supplied.")
            ax = 0
            if data.shape[0] > 2 and data.shape[1] == 2:
                ax = 1
            ind = [slice(None), slice(None)]
            ind[ax] = 0
            y = data[tuple(ind)]
            ind[ax] = 1
            x = data[tuple(ind)]
        elif data.ndim == 1:
            y = data
            
        self.prepareGeometryChange()
        if copy:
            self.yData = y.copy()
        else:
            self.yData = y
            
        if copy and x is not None:
            self.xData = x.copy()
        else:
            self.xData = x
        
        if x is None:
            self.xData = arange(0, self.y.shape[0])

        self.path = None
        #self.specPath = None
        self.xDisp = self.yDisp = None
        self.update()
        self.emit(QtCore.SIGNAL('plotChanged'), self)
        
    def generatePath(self, x, y):
        path = QtGui.QPainterPath()
        
        ## Create all vertices in path. The method used below creates a binary format so that all 
        ## vertices can be read in at once. This binary format may change in future versions of Qt, 
        ## so the original (slower) method is left here for emergencies:
        #self.path.moveTo(x[0], y[0])
        #for i in range(1, y.shape[0]):
            #self.path.lineTo(x[i], y[i])
            
        ## Speed this up using >> operator
        ## Format is:
        ##    numVerts(i4)   0(i4)
        ##    x(f8)   y(f8)   0(i4)    <-- 0 means this vertex does not connect
        ##    x(f8)   y(f8)   1(i4)    <-- 1 means this vertex connects to the previous vertex
        ##    ...
        ##    0(i4)
        ##
        ## All values are big endian--pack using struct.pack('>d') or struct.pack('>i')
        #
        n = x.shape[0]
        # create empty array, pad with extra space on either end
        arr = empty(n+2, dtype=[('x', '>f8'), ('y', '>f8'), ('c', '>i4')])
        # write first two integers
        arr.data[12:20] = struct.pack('>ii', n, 0)
        # Fill array with vertex values
        arr[1:-1]['x'] = x
        arr[1:-1]['y'] = y
        arr[1:-1]['c'] = 1
        # write last 0
        lastInd = 20*(n+1) 
        arr.data[lastInd:lastInd+4] = struct.pack('>i', 0)
        
        # create datastream object and stream into path
        buf = QtCore.QByteArray(arr.data[12:lastInd+4])  # I think one unnecessary copy happens here
        ds = QtCore.QDataStream(buf)
        ds >> path
        
        return path
        
    def boundingRect(self):
        if self.yData is None:
            return QtCore.QRectF()
            
        (x, y) = self.getData()
        xmin = x.min()
        xmax = x.max()
        ymin = y.min()
        ymax = y.max()
        return QtCore.QRectF(xmin, ymin, xmax-xmin, ymax-ymin)

    def paint(self, p, opt, widget):
        if self.xData is None:
            return
        #if self.opts['spectrumMode']:
            #if self.specPath is None:
                
                #self.specPath = self.generatePath(*self.getData())
            #path = self.specPath
        #else:
        if self.path is None:
            self.path = self.generatePath(*self.getData())
        path = self.path
            
        ## Copy pens and apply alpha adjustment
        sp = QtGui.QPen(self.shadow)
        cp = QtGui.QPen(self.pen)
        for pen in [sp, cp]:
            if pen is None:
                continue
            c = pen.color()
            c.setAlpha(c.alpha() * self.opts['alphaHint'])
            pen.setColor(c)
            #pen.setCosmetic(True)
            
        if self.shadow is not None:
            p.setPen(sp)
            p.drawPath(path)
        p.setPen(cp)
        p.drawPath(path)
        
    def free(self):
        del self.xData, self.yData, self.xDisp, self.yDisp, self.path
        
        
class ROIPlotItem(PlotCurveItem):
    def __init__(self, roi, data, img, axes=(0,1), xVals=None, color=None):
        self.roi = roi
        self.roiData = data
        self.roiImg = img
        self.axes = axes
        self.xVals = xVals
        PlotCurveItem.__init__(self, self.getRoiData(), x=self.xVals, color=color)
        roi.connect(QtCore.SIGNAL('regionChanged'), self.roiChangedEvent)
        #self.roiChangedEvent()
        
    def getRoiData(self):
        d = self.roi.getArrayRegion(self.roiData, self.roiImg, axes=self.axes)
        if d is None:
            return
        while d.ndim > 1:
            d = d.mean(axis=1)
        return d
        
    def roiChangedEvent(self):
        d = self.getRoiData()
        self.updateData(d, self.xVals)




class UIGraphicsItem(QtGui.QGraphicsItem):
    """Base class for graphics items with boundaries relative to a GraphicsView widget"""
    def __init__(self, view, bounds=None):
        QtGui.QGraphicsItem.__init__(self)
        self._view = view
        if bounds is None:
            self._bounds = QtCore.QRectF(0, 0, 1, 1)
        else:
            self._bounds = bounds
        self._viewRect = self._view.rect()
        self._viewTransform = self.viewTransform()
        self.setNewBounds()
        
    def viewRect(self):
        """Return the viewport widget rect"""
        return self._view.rect()
    
    def viewTransform(self):
        """Returns a matrix that maps viewport coordinates onto scene coordinates"""
        if self._view is None:
            return QtGui.QTransform()
        else:
            return self._view.viewportTransform()
        
    def boundingRect(self):
        if self._view is None:
            self.bounds = self._bounds
        else:
            vr = self._view.rect()
            tr = self.viewTransform()
            if vr != self._viewRect or tr != self._viewTransform:
                self.viewChangedEvent(vr, self._viewRect)
                self._viewRect = vr
                self._viewTransform = tr
                self.setNewBounds()
        #print "viewRect", self._viewRect.x(), self._viewRect.y(), self._viewRect.width(), self._viewRect.height()
        #print "bounds", self.bounds.x(), self.bounds.y(), self.bounds.width(), self.bounds.height()
        return self.bounds

    def setNewBounds(self):
        bounds = QtCore.QRectF(
            QtCore.QPointF(self._bounds.left()*self._viewRect.width(), self._bounds.top()*self._viewRect.height()),
            QtCore.QPointF(self._bounds.right()*self._viewRect.width(), self._bounds.bottom()*self._viewRect.height())
        )
        bounds.adjust(0.5, 0.5, 0.5, 0.5)
        self.bounds = self.viewTransform().inverted()[0].mapRect(bounds)
        self.prepareGeometryChange()

    def viewChangedEvent(self, newRect, oldRect):
        """Called when the view widget is resized"""
        pass
        
    def unitRect(self):
        return self.viewTransform().inverted()[0].mapRect(QtCore.QRectF(0, 0, 1, 1))

    def paint(self, *args):
        pass








class ScaleItem(QtGui.QGraphicsWidget):
    def __init__(self, orientation, pen=None, linkView=None, parent=None):
        """GraphicsItem showing a single plot axis with ticks and values. Can be configured to fit on any side of a plot, and can automatically synchronize its displayed scale with ViewBox items."""
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.orientation = orientation
        if orientation not in ['left', 'right', 'top', 'bottom']:
            raise Exception("Orientation argument must be one of 'left', 'right', 'top', or 'bottom'.")
        if orientation in ['left', 'right']:
            self.setMinimumWidth(15)
            self.setSizePolicy(QtGui.QSizePolicy(
                QtGui.QSizePolicy.Minimum,
                QtGui.QSizePolicy.Expanding
            ))
        else:
            self.setMinimumHeight(15)
            self.setSizePolicy(QtGui.QSizePolicy(
                QtGui.QSizePolicy.Expanding,
                QtGui.QSizePolicy.Minimum
            ))
            
        self.textHeight = 10
            
        self.setRange(0, 1)
        
        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(100, 100, 100))
        self.setPen(pen)
        
        self.linkedView = None
        if linkView is not None:
            self.linkToView(linkView)
            
        self.tickLength = 10
        
        
    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setRange(self, mn, mx):
        self.range = [mn, mx]
        self.update()
        
    def linkToView(self, view):
        if self.orientation in ['right', 'left']:
            signal = QtCore.SIGNAL('yRangeChanged')
        else:
            signal = QtCore.SIGNAL('xRangeChanged')
            
        if self.linkedView is not None:
            QtCore.QObject.disconnect(view, signal, self.linkedViewChanged)
        self.linkedView = view
        QtCore.QObject.connect(view, signal, self.linkedViewChanged)
        
    def linkedViewChanged(self, _, newRange):
        self.setRange(*newRange)
        
    def boundingRect(self):
        return self.mapRectFromParent(self.geometry())
        
    def paint(self, p, opt, widget):
        p.setPen(self.pen)
        bounds = self.boundingRect()
        if self.orientation == 'left':
            p.drawLine(bounds.topRight(), bounds.bottomRight())
            tickStart = bounds.right()
            tickDir = -1
            axis = 0
        elif self.orientation == 'right':
            p.drawLine(bounds.topLeft(), bounds.bottomLeft())
            tickStart = bounds.left()
            tickDir = 1
            axis = 0
        elif self.orientation == 'top':
            p.drawLine(bounds.bottomLeft(), bounds.bottomRight())
            tickStart = bounds.bottom()
            tickDir = -1
            axis = 1
        elif self.orientation == 'bottom':
            p.drawLine(bounds.topLeft(), bounds.topRight())
            tickStart = bounds.top()
            tickDir = 1
            axis = 1
        
        ## Determine optimal tick spacing
        intervals = [1., 2., 5., 10., 20., 50.]
        dif = abs(self.range[1] - self.range[0])
        if dif == 0.0:
            return
        #print "dif:", dif
        pw = 10 ** (floor(log10(dif))-1)
        for i in range(len(intervals)):
            i1 = i
            if dif / (pw*intervals[i]) < 10:
                break
        
        
        #print "range: %s   dif: %f   power: %f  interval: %f   spacing: %f" % (str(self.range), dif, pw, intervals[i1], sp)
        
        #print "  start at %f,  %d ticks" % (start, num)
        
        ## Number of decimal places to print
        places = max(0, int(3 - log10(dif)))
        
        if axis == 0:
            xs = -bounds.height() / dif
        else:
            xs = bounds.width() / dif
            
        ## draw ticks and text
        for i in [i1, i1+1, i1+2]:  ## draw three different intervals
            ## spacing for this interval
            sp = pw*intervals[i]
            
            ## determine starting tick
            start = ceil(self.range[0] / sp) * sp
        
            ## determine number of ticks
            num = int(dif / sp) + 1
            
            ## length of tick
            h = min(self.tickLength, (self.tickLength*3 / num) - 1.)
            
            ## alpha
            a = min(255, (765. / num) - 1.)
            
            if axis == 0:
                offset = self.range[0] * xs - bounds.height()
            else:
                offset = self.range[0] * xs
            
            for j in range(num):
                v = start + sp * j
                x = (v * xs) - offset
                p1 = [0, 0]
                p2 = [0, 0]
                p1[axis] = tickStart
                p2[axis] = tickStart + h*tickDir
                p1[1-axis] = p2[1-axis] = x
                
                if p1[1-axis] > [bounds.width(), bounds.height()][1-axis]:
                    continue
                p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100, a)))
                p.drawLine(Point(p1), Point(p2))
                if i == i1+1:
                    if abs(v) < .001 or abs(v) >= 10000:
                        vstr = "%g" % v
                    else:
                        vstr = ("%%0.%df" % places) % v
                        
                    textRect = p.boundingRect(QtCore.QRectF(0, 0, 100, 100), QtCore.Qt.AlignCenter, vstr)
                    height = textRect.height()
                    self.textHeight = height
                    if self.orientation == 'left':
                        textFlags = QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStart-100, x-(height/2), 100-self.tickLength, height)
                    elif self.orientation == 'right':
                        textFlags = QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStart+self.tickLength, x-(height/2), 100-self.tickLength, height)
                    elif self.orientation == 'top':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignBottom
                        rect = QtCore.QRectF(x-100, tickStart-self.tickLength-height, 200, height)
                    elif self.orientation == 'bottom':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignTop
                        rect = QtCore.QRectF(x-100, tickStart+self.tickLength, 200, height)
                    
                    p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
                    p.drawText(rect, textFlags, vstr)
                    #p.drawRect(rect)
        
    def show(self):
        if self.orientation in ['left', 'right']:
            self.setMaximumWidth(self.tickLength + 40)
        else:
            self.setMaximumHeight(self.textHeight + self.tickLength)
        QtGui.QGraphicsWidget.show(self)
        
    def hide(self):
        if self.orientation in ['left', 'right']:
            self.setMaximumWidth(0)
        else:
            self.setMaximumHeight(0)
        QtGui.QGraphicsWidget.hide(self)
        
    
        
        
        


#class ViewBox(QtGui.QGraphicsItem, QObjectWorkaround):
class ViewBox(QtGui.QGraphicsWidget):
    """Box that allows internal scaling/panning of children by mouse drag. Not compatible with GraphicsView having the same functionality."""
    def __init__(self, parent=None):
        #QObjectWorkaround.__init__(self)
        QtGui.QGraphicsWidget.__init__(self, parent)
        #self.gView = view
        #self.showGrid = showGrid
        self.range = [[0,1], [0,1]]   ## child coord. range visible [[xmin, xmax], [ymin, ymax]]
        
        self.aspectLocked = False
        QtGui.QGraphicsItem.__init__(self, parent)
        self.setFlag(QtGui.QGraphicsItem.ItemClipsChildrenToShape)
        #self.setFlag(QtGui.QGraphicsItem.ItemClipsToShape)
        
        #self.childScale = [1.0, 1.0]
        #self.childTranslate = [0.0, 0.0]
        self.childGroup = QtGui.QGraphicsItemGroup(self)
        self.currentScale = Point(1, 1)
        
        self.yInverted = False
        #self.invertY()
        self.setZValue(-100)
        #self.picture = None
        self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))
        
        self.drawFrame = True
        
        self.mouseEnabled = [True, True]
    
    def setMouseEnabled(self, x, y):
        self.mouseEnabled = [x, y]
    
    def addItem(self, item):
        if item.zValue() < self.zValue():
            item.setZValue(self.zValue()+1)
        item.setParentItem(self.childGroup)
        #print "addItem:", item, item.boundingRect()
        
    def removeItem(self, item):
        self.scene().removeItem(item)
        
    def resizeEvent(self, ev):
        #self.setRange(self.range, padding=0)
        self.updateMatrix()
        

    def viewRect(self):
        try:
            return QtCore.QRectF(self.range[0][0], self.range[1][0], self.range[0][1]-self.range[0][0], self.range[1][1] - self.range[1][0])
        except:
            print "make qrectf failed:", self.range
            raise
    
    def updateMatrix(self):
        #print "udpateMatrix:"
        #print "  range:", self.range
        vr = self.viewRect()
        translate = Point(vr.center())
        bounds = self.boundingRect()
        #print "  bounds:", bounds
        if vr.height() == 0 or vr.width() == 0:
            return
        scale = Point(bounds.width()/vr.width(), bounds.height()/vr.height())
        #print "  scale:", scale
        m = QtGui.QMatrix()
        
        ## First center the viewport at 0
        self.childGroup.resetMatrix()
        center = self.transform().inverted()[0].map(bounds.center())
        #print "  transform to center:", center
        if self.yInverted:
            m.translate(center.x(), -center.y())
            #print "  inverted; translate", center.x(), center.y()
        else:
            m.translate(center.x(), center.y())
            #print "  not inverted; translate", center.x(), -center.y()
            
        ## Now scale and translate properly
        if self.aspectLocked:
            scale = Point(scale.min())
        if not self.yInverted:
            scale = scale * Point(1, -1)
        m.scale(scale[0], scale[1])
        #print "  scale:", scale
        st = translate
        m.translate(-st[0], -st[1])
        #print "  translate:", st
        self.childGroup.setMatrix(m)
        self.currentScale = scale
        
    def invertY(self, b=True):
        self.yInverted = b
        self.updateMatrix()
        
    def childTransform(self):
        m = self.childGroup.transform()
        m1 = QtGui.QTransform()
        m1.translate(self.childGroup.pos().x(), self.childGroup.pos().y())
        return m*m1
    
    def setAspectLocked(self, s):
        self.aspectLocked = s

    def viewScale(self):
        pr = self.range
        #print "viewScale:", self.range
        xd = pr[0][1] - pr[0][0]
        yd = pr[1][1] - pr[1][0]
        
        #cs = self.canvas().size()
        cs = self.boundingRect()
        return array([cs.width() / xd, cs.height() / yd])

    def scaleBy(self, s, center=None):
        #print "scaleBy", s, center
        xr, yr = self.range
        if center is None:
            xc = (xr[1] + xr[0]) * 0.5
            yc = (yr[1] + yr[0]) * 0.5
        else:
            (xc, yc) = center
        
        x1 = xc + (xr[0]-xc) * s[0]
        x2 = xc + (xr[1]-xc) * s[0]
        y1 = yc + (yr[0]-yc) * s[1]
        y2 = yc + (yr[1]-yc) * s[1]
        
        #print xr, xc, s, (xr[0]-xc) * s[0], (xr[1]-xc) * s[0]
        #print [[x1, x2], [y1, y2]]
        self.setXRange(x1, x2, update=False, padding=0)
        self.setYRange(y1, y2, padding=0)
        #print self.range
        
    def translateBy(self, t, viewCoords=False):
        t = t.astype(float)
        #print "translate:", t, self.viewScale()
        if viewCoords:  ## scale from pixels
            t /= self.viewScale()
        xr, yr = self.range
        #self.setAxisScale(self.xBottom, xr[0] + t[0], xr[1] + t[0])
        #self.setAxisScale(self.yLeft, yr[0] + t[1], yr[1] + t[1])
        self.setXRange(xr[0] + t[0], xr[1] + t[0], update=False, padding=0)
        self.setYRange(yr[0] + t[1], yr[1] + t[1], padding=0)
        #self.replot(autoRange=False)
        #self.updateMatrix()
        
        
    def mouseMoveEvent(self, ev):
        pos = array([ev.pos().x(), ev.pos().y()])
        dif = pos - self.mousePos
        dif *= -1
        self.mousePos = pos
        
        ## Ignore axes if mouse is disabled
        mask = array(self.mouseEnabled, dtype=float)
        
        ## Scale or translate based on mouse button
        if ev.buttons() & QtCore.Qt.LeftButton:
            if not self.yInverted:
                mask *= array([1, -1])
            tr = dif*mask
            self.translateBy(tr, viewCoords=True)
            self.emit(QtCore.SIGNAL('rangeChangedManually'), self.mouseEnabled)
        elif ev.buttons() & QtCore.Qt.RightButton:
            dif = ev.screenPos() - ev.lastScreenPos()
            dif = array([dif.x(), dif.y()])
            dif[0] *= -1
            s = ((mask * 0.02) + 1) ** dif
            #print mask, dif, s
            self.scaleBy(s, Point(self.childGroup.transform().inverted()[0].map(ev.buttonDownPos(QtCore.Qt.RightButton))))
            self.emit(QtCore.SIGNAL('rangeChangedManually'), self.mouseEnabled)
        
    def mousePressEvent(self, ev):
        self.mousePos = array([ev.pos().x(), ev.pos().y()])
        self.pressPos = self.mousePos.copy()
        #Qwt.QwtPlot.mousePressEvent(self, ev)
        
    def mouseReleaseEvent(self, ev):
        pos = array([ev.pos().x(), ev.pos().y()])
        #if sum(abs(self.pressPos - pos)) < 3:  ## Detect click
            #if ev.button() == QtCore.Qt.RightButton:
                #self.ctrlMenu.popup(self.mapToGlobal(ev.pos()))
        self.mousePos = pos
        #Qwt.QwtPlot.mouseReleaseEvent(self, ev)
        
    def setRange(self, ax, min, max, padding=0.02, update=True):
        if ax == 0:
            self.setXRange(min, max, update=update, padding=padding)
        else:
            self.setYRange(min, max, update=update, padding=padding)
            
    def setYRange(self, min, max, update=True, padding=0.02):
        #print "setYRange:", min, max
        padding = (max-min) * padding
        min -= padding
        max += padding
        if self.range[1] != [min, max]:
            #self.setAxisScale(self.yLeft, min, max)
            self.range[1] = [min, max]
            #self.ctrl.yMinText.setText('%g' % min)
            #self.ctrl.yMaxText.setText('%g' % max)
            self.emit(QtCore.SIGNAL('yRangeChanged'), self, (min, max))
        if update:
            self.updateMatrix()
        
    def setXRange(self, min, max, update=True, padding=0.02):
        #print "setXRange:", min, max
        padding = (max-min) * padding
        min -= padding
        max += padding
        if self.range[0] != [min, max]:
            #self.setAxisScale(self.xBottom, min, max)
            self.range[0] = [min, max]
            #self.ctrl.xMinText.setText('%g' % min)
            #self.ctrl.xMaxText.setText('%g' % max)
            self.emit(QtCore.SIGNAL('xRangeChanged'), self, (min, max))
        if update:
            self.updateMatrix()

    def autoRange(self, padding=0.02):
        br = self.childGroup.childrenBoundingRect()
        #print br
        #px = br.width() * padding
        #py = br.height() * padding
        self.setXRange(br.left(), br.right(), padding=padding, update=False)
        self.setYRange(br.top(), br.bottom(), padding=padding)
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.size().width(), self.size().height())
        
    def paint(self, p, opt, widget):
        if self.drawFrame:
            bounds = self.boundingRect()
            p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
            #p.fillRect(bounds, QtGui.QColor(0, 0, 0))
            p.drawRect(bounds)




class GridItem(UIGraphicsItem):
    def __init__(self, view, bounds=None, *args):
        UIGraphicsItem.__init__(self, view, bounds)
        #QtGui.QGraphicsItem.__init__(self, *args)
        self.setFlag(QtGui.QGraphicsItem.ItemClipsToShape)
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
        self.picture = None
        
        
    def viewChangedEvent(self, newRect, oldRect):
        self.picture = None
        
    def paint(self, p, opt, widget):
        #p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
        #p.drawRect(self.boundingRect())
        
        ## draw picture
        if self.picture is None:
            #print "no pic, draw.."
            self.generatePicture()
        p.drawPicture(0, 0, self.picture)
        #print "draw"
        
        
    def generatePicture(self):
        self.picture = QtGui.QPicture()
        p = QtGui.QPainter()
        p.begin(self.picture)
        
        dt = self.viewTransform().inverted()[0]
        vr = self.viewRect()
        unit = self.unitRect()
        dim = [vr.width(), vr.height()]
        lvr = self.boundingRect()
        ul = array([lvr.left(), lvr.top()])
        br = array([lvr.right(), lvr.bottom()])
        
        texts = []
        
        if ul[1] > br[1]:
            x = ul[1]
            ul[1] = br[1]
            br[1] = x
        
        for i in range(2, -1, -1):   ## Draw three different scales of grid
            
            dist = br-ul
            nlTarget = 10.**i
            d = 10. ** floor(log10(abs(dist/nlTarget))+0.5)
            ul1 = floor(ul / d) * d
            br1 = ceil(br / d) * d
            dist = br1-ul1
            nl = (dist / d) + 0.5
            for ax in range(0,2):  ## Draw grid for both axes
                ppl = dim[ax] / nl[ax]
                c = clip(3.*(ppl-3), 0., 30.)
                linePen = QtGui.QPen(QtGui.QColor(255, 255, 255, c)) 
                textPen = QtGui.QPen(QtGui.QColor(255, 255, 255, c*2)) 
                
                bx = (ax+1) % 2
                for x in range(0, int(nl[ax])):
                    p.setPen(linePen)
                    p1 = array([0.,0.])
                    p2 = array([0.,0.])
                    p1[ax] = ul1[ax] + x * d[ax]
                    p2[ax] = p1[ax]
                    p1[bx] = ul[bx]
                    p2[bx] = br[bx]
                    p.drawLine(QtCore.QPointF(p1[0], p1[1]), QtCore.QPointF(p2[0], p2[1]))
                    if i < 2:
                        p.setPen(textPen)
                        if ax == 0:
                            x = p1[0] + unit.width()
                            y = ul[1] + unit.height() * 8.
                        else:
                            x = ul[0] + unit.width()*3
                            y = p1[1] + unit.height()
                        texts.append((QtCore.QPointF(x, y), "%g"%p1[ax]))
        tr = self.viewTransform()
        tr.scale(1.5, 1.5)
        p.setWorldTransform(tr.inverted()[0])
        for t in texts:
            x = tr.map(t[0])
            p.drawText(x, t[1])
        p.end()
