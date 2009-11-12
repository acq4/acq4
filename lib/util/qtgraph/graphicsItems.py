# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from numpy import *
import scipy.weave as weave
from scipy.weave import converters
from lib.util.MetaArray import MetaArray
from lib.util.debug import *
from Point import *
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
    def __init__(self, text, html=False, color=None, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.item = QtGui.QGraphicsTextItem(self)
        if color is not None:
            self.setColor(color)
        self.setText(text, html)
            
    def setColor(self, color):
        self.color = color
        self.item.setDefaultTextColor(color)
        
    def setText(self, text, html=False):
        self.text = text
        if html:
            self.item.setHtml(text)
        else:
            self.item.setPlainText(text)
        
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


class PlotCurveItem(QtGui.QGraphicsWidget):
    """Class representing a single plot curve."""
    def __init__(self, y=None, x=None, copy=False, pen=None, shadow=None, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        
        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(200, 200, 200))
        self.pen = pen
        
        self.shadow = shadow
        #QObjectWorkaround.__init__(self)
        #if type(color) is types.TupleType:
            #self.color = color
            #self.autoColor = False
        #else:
            #self.color = color
            #self.autoColor = True
        if y is not None:
            self.updateData(y, x, copy)
        else:
            self.x = None
            self.y = None
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setShadowPen(self, pen):
        self.shadow = pen
        self.update()

    def updateData(self, data, x=None, copy=False):
        if not isinstance(data, ndarray) or data.ndim > 2:
            raise Exception("Plot data must be 1 or 2D ndarray or MetaArray")
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
            self.y = y.copy()
        else:
            self.y = y
            
        if copy and x is not None:
            self.x = x.copy()
        else:
            self.x = x
        
        if x is None:
            self.x = range(0, self.y.shape[0])

        
        #self.meta = (type(data) is MetaArray)
        
        #if self.data.ndim == 1:
            #self.data.shape = (1,) + self.data.shape
            #if self.meta:
                #if len(self.data._info) == 2:
                    #self.data._info.insert(0, self.data._info[1])
                #else:
                    #self.data._info.insert(0, {})
            
            
        #if xColumn is not None:
            #self.data._info[1]['values'] = self.data[xColumn]
            #yCols = range(0, self.data.shape[0])
            #yCols.remove(xColumn)
        
        #if self.meta:
            #if not self.data._info[1].has_key('values'):
                #if self.xVals is None:
                    #self.data._info[1]['values'] = arange(0, self.data.shape[1])
                #else:
                    #self.data._info[1]['values'] = self.xVals
            
        #self.xscale = 1.0
        #self.yscales = [1.0] * data.shape[0]
        
        self.path = QtGui.QPainterPath()
        
        ## Create all vertices in path. The method used below creates a binary format so that all 
        ## vertices can be read in at once. This binary format may change in future versions, 
        ## so the original (slower) method is left here for emergencies:
        #self.path.moveTo(x[0], y[0])
        #for i in range(1, y.shape[0]):
            #self.path.lineTo(x[i], y[i])
            
        ## Speed this up using >> operator
        ## Format is:
        ##    numVerts(i4)   0(i4)
        ##    x(f8)   y(f8)   0(i4)    <-- 0 means this vert. does not connect
        ##    x(f8)   y(f8)   1(i4)    <-- 1 means this vert. connects to the previous vert.
        ##    ...
        ##    0(i4)
        ##
        ## All values are big endian--pack using struct.pack('>d') or struct.pack('>i')
        #
        n = self.x.shape[0]
        arr = empty(n, dtype=[('x', '>f8'), ('y', '>f8'), ('c', '>i4')])
        arr['x'] = self.x
        arr['y'] = self.y
        arr['c'] = 1
        buf = QtCore.QByteArray(struct.pack('>ii', n, 0) + arr.tostring() + struct.pack('>i', 0))
        ds = QtCore.QDataStream(buf)
        ds >> self.path
           
           
        #self.makeBrushes()
        self.update()
        self.emit(QtCore.SIGNAL('plotChanged'), self)
        

    #def makePath(self):
        #self.path = []
        #if self.x is not None:
            #xVals = self.xVals
        #elif self.meta:
            #xVals = self.data.xvals(1)
        #else:
            #xVals = range(0, self.data.shape[1])
            
        #for i in range(0, self.data.shape[0]):
            #path = QtGui.QPainterPath()
            #path.moveTo(xVals[0], self.data[i,0])
            #for j in range(1, self.data.shape[1]):
                #path.lineTo(xVals[j], self.data[i,j])
            #self.paths.append(path)

    #def numColumns(self):
        #return self.data.shape[0]

    def boundingRect(self):
        if self.y is None:
            return QtCore.QRectF()
            
        xmin = self.x.min()
        xmax = self.x.max()
        ymin = self.y.min()
        ymax = self.y.max()
        return QtCore.QRectF(xmin, ymin, xmax-xmin, ymax-ymin)

    def paint(self, p, opt, widget):
        if self.shadow is not None:
            p.setPen(self.shadow)
            p.drawPath(self.path)
        p.setPen(self.pen)
        p.drawPath(self.path)
        
            ##for j in range(1, self.data.shape[1]):
                ##if self.meta:
                    ##p.drawLine(QtCore.QPointF(self.data.xVals(1)[j-1], self.data[i][j-1]), QtCore.QPointF(self.data.xVals(1)[j], self.data[i][j]))
                ##else:
                    ##p.drawLine(QtCore.QPointF(j-1, self.data[i][j-1]), QtCore.QPointF(j, self.data[i][j]))
            
            #if self.meta and widget is not None:
                #m = QtGui.QMatrix(p.worldMatrix())
                #p.resetMatrix()
                #legend = "%s (%s)" % (self.data._info[0]['cols'][i]['name'], self.data._info[0]['cols'][i]['units'])
                #p.drawText(QtCore.QRectF(0, 20*i, widget.width()-10, 20), QtCore.Qt.AlignRight, legend)
                #p.setWorldMatrix(m)
        #if self.meta:
            #p.resetMatrix()
            #p.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150)))
            #p.drawText(QtCore.QRectF(0, widget.height()-50, widget.width()-10, 20), QtCore.Qt.AlignRight, "%s (%s)" % (self.data._info[1]['name'], self.data._info[1]['units']))
        
            
    
    #def makeBrushes(self):
        #self.brushes = []
        #for i in range(0, self.data.shape[0]):
            #if self.autoColor:
                #c = self.intcolor(i+self.color)
                #self.brushes.append(QtGui.QPen(QtGui.QColor(*c)))
            #else:
                #self.brushes.append(QtGui.QPen(QtGui.QColor(*self.color)))
        
    #def intcolor(self, ind):
        #x = (ind * 280) % (256*3)
        #r = clip(255-abs(x), 0, 255) + clip(255-abs(x-768), 0, 255)
        #g = clip(255-abs(x-256), 0, 255)
        #b = clip(255-abs(x-512), 0, 255)
        #return (r, g, b)
    

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


#class Frame(QtGui.QGraphicsItem):
    #"""Axis and frame class. 
    
#Initialization options:
    #parent=None      Sets the parent widget
    #region=None      Determines where the boundaries of the object are.
                                      #Coordinates are relative to the view if followView=True
    #followView=True  The object stays in the same position on the screen regardless 
                                      #of the scene coordinates.
    #frame=False      Draws a rectangle with tickmarks around the object boundaries
    #frameTicks=None  Determines whether and how to draw ticks on the frame.
    #axes=True        Determines whether and where to draw axes
    #axisTicks=None   Determines whether and how to draw ticks on the axes.
    #"""
    
    #def __init__(self, parent=None, followView=True, region=None, ticks=None):
        #QtGui.QGraphicsItem.__init__(self, parent)
        #self.ticks = ticks
        #self.follow = followView
        #self._region = region
        #self.pen = QtGui.QPen(QtGui.QColor(100, 100, 100))
        #self._view = None
        #self._viewRect = None
        #self.bounds = None
        
        #if not self.follow:
            #self.bounds = self.region
        
    #def view(self):
        #if self._view is None:
            #self._view = self.scene().views()[0]
        #return self._view
        
    #def viewMatrix(self):
        #return self.view().viewportTransform().inverted()[0]
        
    #def viewRect(self):
        #if self._viewRect is None:
            #self._viewRect = self.viewMatrix().mapRect(self.view().rect())
        #return self._viewRect
        
    #def viewScale(self):
        #m = self.viewMatrix()
        #unit = m.mapRect(QtCore.QRectF(0, 0, 1, 1))
        #return (unit.width(), unit.height())
        
    #def boundingRect(self):
        #if self.follow:
            #if self._region is True:
                #self._region = QtCore.QRectF(0, 0, 1, 1)
            #vr = self.view().rect()
            #size = QtCore.QPointF(vr.width(), vr.height())
            #scaled = QtCore.QRectF(
                #QtCore.QPointF(self._region.left()*vr.width(), self._region.bottom()*vr.height()),
                #QtCore.QPointF(self._region.right()*vr.width(), self._region.top()*vr.height())
            #)
            #return self.viewMatrix().mapRect(scaled)
        #else:
            #return self._region
        
    #def paint(self, p, opt, widget):
        #p.setPen(self.pen)
        #p.drawRect(self.boundingRect())
        #print self.viewScale()
        ##m = p.transform()
        #p.scale(*self.viewScale())
        #p.drawText(self.boundingRect(), "text")
        ##p.setTransform(m)




class UIGraphicsItem(QtGui.QGraphicsItem):
    """Base class for graphics items with boundaries relative to a view widget"""
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






class ScaleItem(QtGui.QGraphicsWidget):
    def __init__(self, orientation, pen=None, linkView=None, parent=None):
        QtGui.QGraphicsWidget.__init__(self, parent)
        self.orientation = orientation
        if orientation not in ['left', 'right', 'top', 'bottom']:
            raise Exception("Orientation argument must be one of 'left', 'right', 'top', or 'bottom'.")
            
        self.setRange(0, 1)
        
        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(100, 100, 100))
        self.setPen(pen)
        
        self.linkedView = None
        if linkView is not None:
            self.linkToView(linkView)
        
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
        pw = 10 ** (floor(log10(dif))-1)
        for i in range(len(intervals)):
            i1 = i
            if dif / (pw*intervals[i]) < 10:
                break
        
        
        #print "range: %s   dif: %f   power: %f  interval: %f   spacing: %f" % (str(self.range), dif, pw, intervals[i1], sp)
        
        #print "  start at %f,  %d ticks" % (start, num)
        
        ## Number of decimal places to print
        places = max(2, int(3 - log10(dif)))
        #print dif, places
        
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
            h = min(15, (45. / num) - 1.)
            
            ## alpha
            a = min(255, (765. / num) - 1.)
            
            p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100, a)))
            if axis == 0:
                offset = self.range[0] * xs - bounds.height()
            else:
                offset = self.range[0] * xs
            
            for j in range(num):
                v = start + sp * j
                x = (v * xs) - offset
                #vals.append(x)
                p1 = [0, 0]
                p2 = [0, 0]
                p1[axis] = tickStart
                p2[axis] = tickStart + h*tickDir
                p1[1-axis] = p2[1-axis] = x
                p.drawLine(Point(p1), Point(p2))
                if i > i1:
                    if self.orientation == 'left':
                        textFlags = QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStart-100, x-15, 85, 30)
                    elif self.orientation == 'right':
                        textFlags = QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStart+15, x-15, 85, 30)
                    elif self.orientation == 'top':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignBottom
                        rect = QtCore.QRectF(x-100, tickStart-45, 200, 30)
                    elif self.orientation == 'bottom':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignTop
                        rect = QtCore.QRectF(x-100, tickStart+15, 200, 30)
                    
                    #coords = [0, 0, 0, 0]
                    #coords[axis] = tickStart# + 20*tickDir
                    #coords[1-axis] = x# - 100*tickDir
                    ##coords[axis+2] = 15
                    ##coords[3-axis] = 200
                    #coords[0] -= 100 + 30*(1-axis)
                    #coords[1] += 15*tickDir
                    #coords[2] = 200
                    #coords[3] = 30
                    #rect = QtCore.QRectF(*coords)
                    p.drawText(rect, textFlags, ("%%0.%dg" % places) % v)
        #print "  vals:", vals
        
        
        
        
        


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
    
    def addItem(self, item):
        if item.zValue() < self.zValue():
            item.setZValue(self.zValue()+1)
        item.setParentItem(self.childGroup)
        
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
        
        self.setXRange(x1, x2, update=False)
        self.setYRange(y1, y2)
        
    def translateBy(self, t, viewCoords=False):
        t = t.astype(float)
        #print "translate:", t, self.viewScale()
        if viewCoords:  ## scale from pixels
            t /= self.viewScale()
        xr, yr = self.range
        #self.setAxisScale(self.xBottom, xr[0] + t[0], xr[1] + t[0])
        #self.setAxisScale(self.yLeft, yr[0] + t[1], yr[1] + t[1])
        self.setXRange(xr[0] + t[0], xr[1] + t[0], update=False)
        self.setYRange(yr[0] + t[1], yr[1] + t[1])
        #self.replot(autoRange=False)
        #self.updateMatrix()
        
        
    def mouseMoveEvent(self, ev):
        pos = array([ev.pos().x(), ev.pos().y()])
        dif = pos - self.mousePos
        dif *= -1
        self.mousePos = pos
        
        ## Ignore axes if mouse is disabled
        mask = array([1, 1])
        #if self.ctrl.xMouseCheck.isChecked():
            #mask[0] = 1
            #self.setManualXScale()
        #if self.ctrl.yMouseCheck.isChecked():
            #mask[1] = 1
            #self.setManualYScale()
        
        ## Scale or translate based on mouse button
        if ev.buttons() & QtCore.Qt.LeftButton:
            if not self.yInverted:
                mask *= array([1, -1])
            self.translateBy(dif * mask, viewCoords=True)
        elif ev.buttons() & QtCore.Qt.RightButton:
            dif = ev.screenPos() - ev.lastScreenPos()
            dif = array([dif.x(), dif.y()])
            dif[0] *= -1
            s = ((mask * 0.02) + 1) ** dif
            #print "scale:", dif, s
            #cPos = self.canvas().pos()
            #cPos = array([cPos.x(), cPos.y()])
            self.scaleBy(s, Point(self.childGroup.transform().inverted()[0].map(ev.buttonDownPos(QtCore.Qt.RightButton))))
            
        #Qwt.QwtPlot.mouseMoveEvent(self, ev)
        
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
        
    def setYRange(self, min, max, update=True):
        #print "setYRange:", min, max
        if self.range[1] != [min, max]:
            #self.setAxisScale(self.yLeft, min, max)
            self.range[1] = [min, max]
            #self.ctrl.yMinText.setText('%g' % min)
            #self.ctrl.yMaxText.setText('%g' % max)
            self.emit(QtCore.SIGNAL('yRangeChanged'), self, (min, max))
        if update:
            self.updateMatrix()
        
    def setXRange(self, min, max, update=True):
        #print "setXRange:", min, max
        if self.range[0] != [min, max]:
            #self.setAxisScale(self.xBottom, min, max)
            self.range[0] = [min, max]
            #self.ctrl.xMinText.setText('%g' % min)
            #self.ctrl.xMaxText.setText('%g' % max)
            self.emit(QtCore.SIGNAL('xRangeChanged'), self, (min, max))
        if update:
            self.updateMatrix()

    def autoRange(self, padding=0.05):
        br = self.childGroup.childrenBoundingRect()
        px = br.width() * padding
        py = br.height() * padding
        self.setXRange(br.left()-px, br.right()+px, update=False)
        self.setYRange(br.top()-py, br.bottom()+py)

    #def mousePressEvent(self, ev):
        #if ev.buttons() == QtCore.Qt.RightButton or ev.buttons() == QtCore.Qt.LeftButton:
            #pass
        #else:
            #print "passing on press"
            #ev.ignore()
        
    #def mouseMoveEvent(self, ev):
        #print "Mouse move"
        #d = ev.scenePos() - ev.lastScenePos()
        #if ev.buttons() == QtCore.Qt.RightButton:
            ##if self.aspectLocked:
                ##self.childScale[0] *= 1.02 ** -d.y()
            ##else:
                ##self.childScale[0] *= 1.02 ** d.x()
            ##self.childScale[1] *= 1.02 ** -d.y()
            ##self.updateChildTransform()
            #self.scale(1.02 ** d.x(), 1.02 ** -d.y())
            
        #elif ev.buttons() == QtCore.Qt.LeftButton:
            #self.translate(-d.x(), -d.y())
            ##self.childTranslate[0] += d.x() / self.childScale[0]
            ##self.childTranslate[1] += d.y() / self.childScale[1]
            ##self.updateMatrix()
        
    #def mouseReleaseEvent(self, ev):
        #pass
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.size().width(), self.size().height())
        
        #print 'boundingRect'
        #if self.gView is None:
            #self.bounds = self._bounds
        #else:
            #vr = self.gView.rect()
            
            #if self._viewRect is None or vr != self._viewRect:
                #if self._viewRect is not None:
                    ### Rescale children to fit new widget size
                    #self.childScale[0] *= float(vr.width()) / self._viewRect.width()
                    #self.childScale[1] *= float(vr.height()) / self._viewRect.height()
                #self._viewRect = vr
                #self.bounds = QtCore.QRectF(
                    #QtCore.QPointF(self._bounds.left()*vr.width(), self._bounds.top()*vr.height()),
                    #QtCore.QPointF(self._bounds.right()*vr.width(), self._bounds.bottom()*vr.height())
                #)
                #self.prepareGeometryChange()
                #self.picture = None
        #self.childGroup.setPos(self.bounds.center())
        #return self.bounds
        
        
    def paint(self, p, opt, widget):
        if self.drawFrame:
            bounds = self.boundingRect()
            p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
            #p.fillRect(bounds, QtGui.QColor(0, 0, 0))
            p.drawRect(bounds)
            #print "draw rect", bounds
        
        #if self.picture is None:
            #self.picture = QtGui.QPicture()
            #pp = QtGui.QPainter()
            #pp.begin(self.picture)
            #if self.showGrid:
                #self.drawGrid(pp, opt, widget)
            #pp.end()
        #p.drawPicture(0, 0, self.picture)
            
            
    #def drawGrid(self, p, opt, widget):
        #bounds = self.boundingRect()
        #m = self.childTransform()
        #mi = m.inverted()[0]
        #lBounds = mi.mapRect(bounds)
        #ul = array([lBounds.left(), lBounds.top()])
        #br = array([lBounds.right(), lBounds.bottom()])
        #diag = br-ul
        #dim = array([bounds.width(), bounds.height()])
        
        #for i in [2, 1, 0]:  ## Iterate over scales (roughly 10**i lines per iteration)
            #nlTarget = 10.**i
            
            ### determine line spacing
            #d = 10. ** floor(log10(abs(diag/nlTarget))+0.5)
            
            ### determine start and stop values
            #ul1 = floor(ul / d) * d
            #br1 = ceil(br / d) * d
            
            ### determine number of lines
            #dist = br1-ul1
            #nl = (dist / d) + 0.5
            
            #for ax in [0,1]:  ## Draw grid for both axes
                #bx = (ax+1) % 2
                
                ### determine pixel spacing of lines to set colors
                #ppl = dim[ax] / nl[ax]
                #c = clip(3.*(ppl-3), 0., 30.)
                #linePen = QtGui.QPen(QtGui.QColor(255, 255, 255, c)) 
                #textPen = QtGui.QPen(QtGui.QColor(255, 255, 255, c*2)) 
        
                ### draw lines
                #for x in range(0, int(nl[ax])):
                    #p.setPen(linePen)
                    #p1 = array([0.,0.])
                    #p2 = array([0.,0.])
                    #p1[ax] = ul1[ax] + x * d[ax]
                    #p2[ax] = p1[ax]
                    #p1[bx] = ul1[bx]
                    #p2[bx] = br1[bx]
                    #p.drawLine(m.map(QtCore.QPointF(p1[0], p1[1])), m.map(QtCore.QPointF(p2[0], p2[1])))
                    #if i < 2:
                        #p.setPen(textPen)
                        #if ax == 0:
                            #x = m.map(p1[0], 0.)[0] + 2
                            #y = dim[1] - 10
                        #else:
                            #x = 10
                            #y = m.map(0., p1[1])[1] - 2
                        #p.drawText(QtCore.QPointF(x, y), "%g"%p1[ax])




