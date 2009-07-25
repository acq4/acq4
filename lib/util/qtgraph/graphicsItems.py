# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from numpy import *
import scipy.weave as weave
from scipy.weave import converters
from lib.util.MetaArray import MetaArray
import types, sys

## Multiple inheritance not allowed in PyQt. Retarded workaround:
class QObjectWorkaround:
    def __init__(self):
        self._qObj_ = QtCore.QObject()
    def __getattr__(self, attr):
        if attr == '_qObj_':
            raise Exception("QObjectWorkaround not initialized!")
        return getattr(self._qObj_, attr)
    def connect(self, *args):
        return QtCore.QObject.connect(self._qObj_, *args)

class ImageItem(QtGui.QGraphicsPixmapItem):
    def __init__(self, image=None, copy=True, *args):
        self.qimage = QtGui.QImage()
        self.pixmap = None
        self.useWeave = True
        self.blackLevel = None
        self.whiteLevel = None
        self.image = None
        self.clipLevel = None
        QtGui.QGraphicsPixmapItem.__init__(self, *args)
        #self.pixmapItem = QtGui.QGraphicsPixmapItem(self)
        if image is not None:
            self.updateImage(image, copy, autoRange=True)
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        
        
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
                print "Weave compile failed, falling back to slower version."
                sys.excepthook(*sys.exc_info())
            self.image.shape = shape
            im = ((self.image - black) * scale).clip(0.,255.).astype(ubyte)
                

        try:
            im1 = empty((im.shape[axh['y']], im.shape[axh['x']], 4), dtype=ubyte)
        except:
            print im.shape, axh
            raise
            
        # Fill image 
        if im.ndim == 2:
            im2 = im.transpose(axh['y'], axh['x'])
            im1[..., 0] = im2
            im1[..., 1] = im2
            im1[..., 2] = im2
            im1[..., 3] = 255
        elif im.ndim == 3:
            im2 = im.transpose(axh['y'], axh['x'], axh['c'])
            
            for i in range(0, im.shape[axh['c']]):
                im1[..., i] = im2[..., i]
            for i in range(im.shape[axh['c']], 4):
                im1[..., i] = 255
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
        qimage = QtGui.QImage(self.ims, im1.shape[1], im1.shape[0], QtGui.QImage.Format_RGB32)
        self.pixmap = QtGui.QPixmap.fromImage(qimage)
        ##del self.ims
        self.setPixmap(self.pixmap)
        self.update()
        
    def getPixmap(self):
        return self.pixmap.copy()


class Plot(QtGui.QGraphicsItem, QObjectWorkaround):
    def __init__(self, data, xVals = None, copy=False, color=0, parent=None):
        QtGui.QGraphicsItem.__init__(self, parent)
        QObjectWorkaround.__init__(self)
        if type(color) is types.TupleType:
            self.color = color
            self.autoColor = False
        else:
            self.color = color
            self.autoColor = True
        self.updateData(data, xVals, copy)
        self.makeBrushes()
        self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        

    def updateData(self, data, xVals=None, copy=False):
        self.prepareGeometryChange()
        if copy:
            self.data = data.copy()
        else:
            self.data = data
            
            
        if copy and xVals is not None:
            self.xVals = xVals.copy()
        else:
            self.xVals = xVals
        
        if type(data) not in [MetaArray, ndarray] or data.ndim > 2:
            raise Exception("Plot data must be 1 or 2D ndarray or MetaArray")
        
        self.meta = (type(data) is MetaArray)
        
        if self.data.ndim == 1:
            self.data.shape = (1,) + self.data.shape
            if self.meta:
                if len(self.data._info) == 2:
                    self.data._info.insert(0, self.data._info[1])
                else:
                    self.data._info.insert(0, {})
            
            
        #if xColumn is not None:
            #self.data._info[1]['values'] = self.data[xColumn]
            #yCols = range(0, self.data.shape[0])
            #yCols.remove(xColumn)
        
        if self.meta:
            if not self.data._info[1].has_key('values'):
                if self.xVals is None:
                    self.data._info[1]['values'] = arange(0, self.data.shape[1])
                else:
                    self.data._info[1]['values'] = self.xVals
            
        #self.xscale = 1.0
        #self.yscales = [1.0] * data.shape[0]
        self.makePaths()
        self.update()
        self.emit(QtCore.SIGNAL('plotChanged'), self)
        

    def makePaths(self):
        self.paths = []
        if self.xVals is not None:
            xVals = self.xVals
        elif self.meta:
            xVals = self.data.xVals(1)
        else:
            xVals = range(0, self.data.shape[1])
            
        for i in range(0, self.data.shape[0]):
            path = QtGui.QPainterPath()
            path.moveTo(xVals[0], self.data[i,0])
            for j in range(1, self.data.shape[1]):
                path.lineTo(xVals[j], self.data[i,j])
            self.paths.append(path)

    def numColumns(self):
        return self.data.shape[0]

    def boundingRect(self):
        if hasattr(self.data, 'xVals'):
            xmin = self.data.xVals(1).min()
            xmax = self.data.xVals(1).max()
        elif self.xVals is not None:
            xmin = self.xVals.min()
            xmax = self.xVals.max()
        else: 
            xmin = 0
            xmax = self.data.shape[1]
        ymin = self.data.min()
        return QtCore.QRectF(xmin, ymin, xmax-xmin, self.data.max() - ymin)

    def paint(self, p, opt, widget):
        for i in range(0, self.data.shape[0]):
            p.setPen(self.brushes[i])
            p.drawPath(self.paths[i])
            
            #for j in range(1, self.data.shape[1]):
                #if self.meta:
                    #p.drawLine(QtCore.QPointF(self.data.xVals(1)[j-1], self.data[i][j-1]), QtCore.QPointF(self.data.xVals(1)[j], self.data[i][j]))
                #else:
                    #p.drawLine(QtCore.QPointF(j-1, self.data[i][j-1]), QtCore.QPointF(j, self.data[i][j]))
            
            if self.meta:
                m = QtGui.QMatrix(p.worldMatrix())
                p.resetMatrix()
                legend = "%s (%s)" % (self.data._info[0]['cols'][i]['name'], self.data._info[0]['cols'][i]['units'])
                p.drawText(QtCore.QRectF(0, 20*i, widget.width()-10, 20), QtCore.Qt.AlignRight, legend)
                p.setWorldMatrix(m)
        if self.meta:
            p.resetMatrix()
            p.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150)))
            p.drawText(QtCore.QRectF(0, widget.height()-50, widget.width()-10, 20), QtCore.Qt.AlignRight, "%s (%s)" % (self.data._info[1]['name'], self.data._info[1]['units']))
        
            
    
    def makeBrushes(self):
        self.brushes = []
        for i in range(0, self.data.shape[0]):
            if self.autoColor:
                c = self.intcolor(i+self.color)
                self.brushes.append(QtGui.QPen(QtGui.QColor(*c)))
            else:
                self.brushes.append(QtGui.QPen(QtGui.QColor(*self.color)))
        
    def intcolor(self, ind):
        x = (ind * 280) % (256*3)
        r = clip(255-abs(x), 0, 255) + clip(255-abs(x-768), 0, 255)
        g = clip(255-abs(x-256), 0, 255)
        b = clip(255-abs(x-512), 0, 255)
        return (r, g, b)
    

class ROIPlot(Plot):
    def __init__(self, roi, data, img, axes=(0,1), xVals=None, color=None):
        self.roi = roi
        self.roiData = data
        self.roiImg = img
        self.axes = axes
        self.xVals = xVals
        Plot.__init__(self, self.getRoiData(), xVals=self.xVals, color=color)
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


class Grid(UIGraphicsItem):
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










class ViewBox(QtGui.QGraphicsItem):
    """Box that allows internal scaling/panning of children by mouse drag. Not compatible with GraphicsView having the same functionality."""
    def __init__(self, bounds, view=None, showGrid=False, parent=None):
        self.gView = view
        self.showGrid = showGrid
        self._bounds = bounds
        self._viewRect = None
        self.aspectLocked = False
        QtGui.QGraphicsItem.__init__(self, parent)
        #self.setFlag(QtGui.QGraphicsItem.ItemClipsChildrenToShape)
        self.setFlag(QtGui.QGraphicsItem.ItemClipsToShape)
        
        self.childScale = [1.0, 1.0]
        self.childTranslate = [0.0, 0.0]
        self.childGroup = QtGui.QGraphicsItemGroup(self)
        
        self.invertY()
        self.setZValue(-100)
        
    def addItem(self, item):
        if item.zValue() < self.zValue():
            item.setZValue(self.zValue()+1)
        item.setParentItem(self.childGroup)
        
    def updateChildTransform(self):
        m = QtGui.QTransform()
        m.scale(*self.childScale)
        m.translate(*self.childTranslate)
        self.childGroup.setTransform(m)
        self.picture = None
        self.update()
        
    def invertY(self):
        self.childScale[1] *= -1.0
        self.updateChildTransform()
        
    def childTransform(self):
        m = self.childGroup.transform()
        m1 = QtGui.QTransform()
        m1.translate(self.childGroup.pos().x(), self.childGroup.pos().y())
        return m*m1
    
    def setAspectLocked(self, s):
        self.aspectLocked = s
        
    def mousePressEvent(self, ev):
        if ev.buttons() == QtCore.Qt.RightButton or ev.buttons() == QtCore.Qt.MidButton:
            pass
        else:
            print "passing on press"
            ev.ignore()
        
    def mouseMoveEvent(self, ev):
        d = ev.scenePos() - ev.lastScenePos()
        if ev.buttons() == QtCore.Qt.RightButton:
            if self.aspectLocked:
                self.childScale[0] *= 1.02 ** -d.y()
            else:
                self.childScale[0] *= 1.02 ** d.x()
            self.childScale[1] *= 1.02 ** -d.y()
            self.updateChildTransform()
        elif ev.buttons() == QtCore.Qt.MidButton:
            self.childTranslate[0] += d.x() / self.childScale[0]
            self.childTranslate[1] += d.y() / self.childScale[1]
            self.updateChildTransform()
        
    def mouseReleaseEvent(self, ev):
        pass
        
    def boundingRect(self):
        if self.gView is None:
            self.bounds = self._bounds
        else:
            vr = self.gView.rect()
            
            if self._viewRect is None or vr != self._viewRect:
                if self._viewRect is not None:
                    ## Rescale children to fit new widget size
                    self.childScale[0] *= float(vr.width()) / self._viewRect.width()
                    self.childScale[1] *= float(vr.height()) / self._viewRect.height()
                self._viewRect = vr
                self.bounds = QtCore.QRectF(
                    QtCore.QPointF(self._bounds.left()*vr.width(), self._bounds.top()*vr.height()),
                    QtCore.QPointF(self._bounds.right()*vr.width(), self._bounds.bottom()*vr.height())
                )
                self.prepareGeometryChange()
                self.picture = None
        self.childGroup.setPos(self.bounds.center())
        return self.bounds
        
        
    def paint(self, p, opt, widget):
        bounds = self.boundingRect()
        p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
        p.fillRect(bounds, QtGui.QColor(0, 0, 0))
        p.drawRect(bounds)
        
        if self.picture is None:
            self.picture = QtGui.QPicture()
            pp = QtGui.QPainter()
            pp.begin(self.picture)
            if self.showGrid:
                self.drawGrid(pp, opt, widget)
            pp.end()
        p.drawPicture(0, 0, self.picture)
            
            
    def drawGrid(self, p, opt, widget):
        bounds = self.boundingRect()
        m = self.childTransform()
        mi = m.inverted()[0]
        lBounds = mi.mapRect(bounds)
        ul = array([lBounds.left(), lBounds.top()])
        br = array([lBounds.right(), lBounds.bottom()])
        diag = br-ul
        dim = array([bounds.width(), bounds.height()])
        
        for i in [2, 1, 0]:  ## Iterate over scales (roughly 10**i lines per iteration)
            nlTarget = 10.**i
            
            ## determine line spacing
            d = 10. ** floor(log10(abs(diag/nlTarget))+0.5)
            
            ## determine start and stop values
            ul1 = floor(ul / d) * d
            br1 = ceil(br / d) * d
            
            ## determine number of lines
            dist = br1-ul1
            nl = (dist / d) + 0.5
            
            for ax in [0,1]:  ## Draw grid for both axes
                bx = (ax+1) % 2
                
                ## determine pixel spacing of lines to set colors
                ppl = dim[ax] / nl[ax]
                c = clip(3.*(ppl-3), 0., 30.)
                linePen = QtGui.QPen(QtGui.QColor(255, 255, 255, c)) 
                textPen = QtGui.QPen(QtGui.QColor(255, 255, 255, c*2)) 
        
                ## draw lines
                for x in range(0, int(nl[ax])):
                    p.setPen(linePen)
                    p1 = array([0.,0.])
                    p2 = array([0.,0.])
                    p1[ax] = ul1[ax] + x * d[ax]
                    p2[ax] = p1[ax]
                    p1[bx] = ul1[bx]
                    p2[bx] = br1[bx]
                    p.drawLine(m.map(QtCore.QPointF(p1[0], p1[1])), m.map(QtCore.QPointF(p2[0], p2[1])))
                    if i < 2:
                        p.setPen(textPen)
                        if ax == 0:
                            x = m.map(p1[0], 0.)[0] + 2
                            y = dim[1] - 10
                        else:
                            x = 10
                            y = m.map(0., p1[1])[1] - 2
                        p.drawText(QtCore.QPointF(x, y), "%g"%p1[ax])




