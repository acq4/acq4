from pyqtgraph.Qt import QtGui, QtCore
import numpy as np
from pyqtgraph.Point import Point
import pyqtgraph.debug as debug
import weakref
import pyqtgraph.functions as fn
from GraphicsWidget import GraphicsWidget

class AxisItem(GraphicsWidget):
    def __init__(self, orientation, pen=None, linkView=None, parent=None, maxTickLength=-5):
        """
        GraphicsItem showing a single plot axis with ticks, values, and label.
        Can be configured to fit on any side of a plot, and can automatically synchronize its displayed scale with ViewBox items.
        Ticks can be extended to make a grid.
        """
        
        
        GraphicsWidget.__init__(self, parent)
        self.label = QtGui.QGraphicsTextItem(self)
        self.orientation = orientation
        if orientation not in ['left', 'right', 'top', 'bottom']:
            raise Exception("Orientation argument must be one of 'left', 'right', 'top', or 'bottom'.")
        if orientation in ['left', 'right']:
            #self.setMinimumWidth(25)
            #self.setSizePolicy(QtGui.QSizePolicy(
                #QtGui.QSizePolicy.Minimum,
                #QtGui.QSizePolicy.Expanding
            #))
            self.label.rotate(-90)
        #else:
            #self.setMinimumHeight(50)
            #self.setSizePolicy(QtGui.QSizePolicy(
                #QtGui.QSizePolicy.Expanding,
                #QtGui.QSizePolicy.Minimum
            #))
        #self.drawLabel = False
        
        self.labelText = ''
        self.labelUnits = ''
        self.labelUnitPrefix=''
        self.labelStyle = {'color': '#CCC'}
        
        self.textHeight = 18
        self.tickLength = maxTickLength
        self.scale = 1.0
        self.autoScale = True
            
        self.setRange(0, 1)
        
        if pen is None:
            pen = QtGui.QPen(QtGui.QColor(100, 100, 100))
        self.setPen(pen)
        
        self.linkedView = None
        if linkView is not None:
            self.linkToView(linkView)
            
        self.showLabel(False)
        
        self.grid = False
        #self.setCacheMode(self.DeviceCoordinateCache)
            
    def close(self):
        self.scene().removeItem(self.label)
        self.label = None
        self.scene().removeItem(self)
        
    def setGrid(self, grid):
        """Set the alpha value for the grid, or False to disable."""
        self.grid = grid
        self.update()
        
        
    def resizeEvent(self, ev=None):
        #s = self.size()
        
        ## Set the position of the label
        nudge = 5
        br = self.label.boundingRect()
        p = QtCore.QPointF(0, 0)
        if self.orientation == 'left':
            p.setY(int(self.size().height()/2 + br.width()/2))
            p.setX(-nudge)
            #s.setWidth(10)
        elif self.orientation == 'right':
            #s.setWidth(10)
            p.setY(int(self.size().height()/2 + br.width()/2))
            p.setX(int(self.size().width()-br.height()+nudge))
        elif self.orientation == 'top':
            #s.setHeight(10)
            p.setY(-nudge)
            p.setX(int(self.size().width()/2. - br.width()/2.))
        elif self.orientation == 'bottom':
            p.setX(int(self.size().width()/2. - br.width()/2.))
            #s.setHeight(10)
            p.setY(int(self.size().height()-br.height()+nudge))
        #self.label.resize(s)
        self.label.setPos(p)
        
    def showLabel(self, show=True):
        #self.drawLabel = show
        self.label.setVisible(show)
        if self.orientation in ['left', 'right']:
            self.setWidth()
        else:
            self.setHeight()
        if self.autoScale:
            self.setScale()
        
    def setLabel(self, text=None, units=None, unitPrefix=None, **args):
        if text is not None:
            self.labelText = text
            self.showLabel()
        if units is not None:
            self.labelUnits = units
            self.showLabel()
        if unitPrefix is not None:
            self.labelUnitPrefix = unitPrefix
        if len(args) > 0:
            self.labelStyle = args
        self.label.setHtml(self.labelString())
        self.resizeEvent()
        self.update()
            
    def labelString(self):
        if self.labelUnits == '':
            if self.scale == 1.0:
                units = ''
            else:
                units = u'(x%g)' % (1.0/self.scale)
        else:
            #print repr(self.labelUnitPrefix), repr(self.labelUnits)
            units = u'(%s%s)' % (self.labelUnitPrefix, self.labelUnits)
            
        s = u'%s %s' % (self.labelText, units)
        
        style = ';'.join(['%s: "%s"' % (k, self.labelStyle[k]) for k in self.labelStyle])
        
        return u"<span style='%s'>%s</span>" % (style, s)
        
    def setHeight(self, h=None):
        if h is None:
            h = self.textHeight + max(0, self.tickLength)
            if self.label.isVisible():
                h += self.textHeight
        self.setMaximumHeight(h)
        self.setMinimumHeight(h)
        
        
    def setWidth(self, w=None):
        if w is None:
            w = max(0, self.tickLength) + 40
            if self.label.isVisible():
                w += self.textHeight
        self.setMaximumWidth(w)
        self.setMinimumWidth(w)
        
    def setPen(self, pen):
        self.pen = pen
        self.update()
        
    def setScale(self, scale=None):
        if scale is None:
            #if self.drawLabel:  ## If there is a label, then we are free to rescale the values 
            if self.label.isVisible():
                d = self.range[1] - self.range[0]
                #pl = 1-int(log10(d))
                #scale = 10 ** pl
                (scale, prefix) = fn.siScale(d / 2.)
                if self.labelUnits == '' and prefix in ['k', 'm']:  ## If we are not showing units, wait until 1e6 before scaling.
                    scale = 1.0
                    prefix = ''
                self.setLabel(unitPrefix=prefix)
            else:
                scale = 1.0
        
        
        if scale != self.scale:
            self.scale = scale
            self.setLabel()
            self.update()
        
    def setRange(self, mn, mx):
        if mn in [np.nan, np.inf, -np.inf] or mx in [np.nan, np.inf, -np.inf]:
            raise Exception("Not setting range to [%s, %s]" % (str(mn), str(mx)))
        self.range = [mn, mx]
        if self.autoScale:
            self.setScale()
        self.update()
        
    def linkToView(self, view):
        if self.orientation in ['right', 'left']:
            if self.linkedView is not None and self.linkedView() is not None:
                #view.sigYRangeChanged.disconnect(self.linkedViewChanged)
                ## should be this instead?
                self.linkedView().sigYRangeChanged.disconnect(self.linkedViewChanged)
            self.linkedView = weakref.ref(view)
            view.sigYRangeChanged.connect(self.linkedViewChanged)
            #signal = QtCore.SIGNAL('yRangeChanged')
        else:
            if self.linkedView is not None and self.linkedView() is not None:
                #view.sigYRangeChanged.disconnect(self.linkedViewChanged)
                ## should be this instead?
                self.linkedView().sigXRangeChanged.disconnect(self.linkedViewChanged)
            self.linkedView = weakref.ref(view)
            view.sigXRangeChanged.connect(self.linkedViewChanged)
            #signal = QtCore.SIGNAL('xRangeChanged')
            
        
    def linkedViewChanged(self, view, newRange):
        self.setRange(*newRange)
        
    def boundingRect(self):
        if self.linkedView is None or self.linkedView() is None or self.grid is False:
            rect = self.mapRectFromParent(self.geometry())
            ## extend rect if ticks go in negative direction
            if self.orientation == 'left':
                rect.setRight(rect.right() - min(0,self.tickLength))
            elif self.orientation == 'right':
                rect.setLeft(rect.left() + min(0,self.tickLength))
            elif self.orientation == 'top':
                rect.setBottom(rect.bottom() - min(0,self.tickLength))
            elif self.orientation == 'bottom':
                rect.setTop(rect.top() + min(0,self.tickLength))
            return rect
        else:
            return self.mapRectFromParent(self.geometry()) | self.mapRectFromScene(self.linkedView().mapRectToScene(self.linkedView().boundingRect()))
        
    def paint(self, p, opt, widget):
        prof = debug.Profiler("AxisItem.paint", disabled=True)
        p.setPen(self.pen)
        
        #bounds = self.boundingRect()
        bounds = self.mapRectFromParent(self.geometry())
        
        if self.linkedView is None or self.linkedView() is None or self.grid is False:
            tbounds = bounds
        else:
            tbounds = self.mapRectFromScene(self.linkedView().mapRectToScene(self.linkedView().boundingRect()))
        
        if self.orientation == 'left':
            p.drawLine(bounds.topRight(), bounds.bottomRight())
            tickStart = tbounds.right()
            tickStop = bounds.right()
            tickDir = -1
            axis = 0
        elif self.orientation == 'right':
            p.drawLine(bounds.topLeft(), bounds.bottomLeft())
            tickStart = tbounds.left()
            tickStop = bounds.left()
            tickDir = 1
            axis = 0
        elif self.orientation == 'top':
            p.drawLine(bounds.bottomLeft(), bounds.bottomRight())
            tickStart = tbounds.bottom()
            tickStop = bounds.bottom()
            tickDir = -1
            axis = 1
        elif self.orientation == 'bottom':
            p.drawLine(bounds.topLeft(), bounds.topRight())
            tickStart = tbounds.top()
            tickStop = bounds.top()
            tickDir = 1
            axis = 1
        
        ## Determine optimal tick spacing
        #intervals = [1., 2., 5., 10., 20., 50.]
        #intervals = [1., 2.5, 5., 10., 25., 50.]
        intervals = [1., 2., 10., 20., 100.]
        dif = abs(self.range[1] - self.range[0])
        if dif == 0.0:
            return
        #print "dif:", dif
        pw = 10 ** (np.floor(np.log10(dif))-1)
        for i in range(len(intervals)):
            i1 = i
            if dif / (pw*intervals[i]) < 10:
                break
        
        textLevel = i1  ## draw text at this scale level
        
        #print "range: %s   dif: %f   power: %f  interval: %f   spacing: %f" % (str(self.range), dif, pw, intervals[i1], sp)
        
        #print "  start at %f,  %d ticks" % (start, num)
        
        
        if axis == 0:
            xs = -bounds.height() / dif
        else:
            xs = bounds.width() / dif
        
        prof.mark('init')
            
        tickPositions = set() # remembers positions of previously drawn ticks
        ## draw ticks and generate list of texts to draw
        ## (to improve performance, we do not interleave line and text drawing, since this causes unnecessary pipeline switching)
        ## draw three different intervals, long ticks first
        texts = []
        for i in reversed([i1, i1+1, i1+2]):
            if i > len(intervals):
                continue
            ## spacing for this interval
            sp = pw*intervals[i]
            
            ## determine starting tick
            start = np.ceil(self.range[0] / sp) * sp
            
            ## determine number of ticks
            num = int(dif / sp) + 1
            
            ## last tick value
            last = start + sp * num
            
            ## Number of decimal places to print
            maxVal = max(abs(start), abs(last))
            places = max(0, 1-int(np.log10(sp*self.scale)))
        
            ## length of tick
            h = np.clip((self.tickLength*3 / num) - 1., min(0, self.tickLength), max(0, self.tickLength))
            
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
                p2[axis] = tickStop + h*tickDir
                p1[1-axis] = p2[1-axis] = x
                
                if p1[1-axis] > [bounds.width(), bounds.height()][1-axis]:
                    continue
                if p1[1-axis] < 0:
                    continue
                p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100, a)))
                # draw tick only if there is none
                tickPos = p1[1-axis]
                if tickPos not in tickPositions:
                    p.drawLine(Point(p1), Point(p2))
                    tickPositions.add(tickPos)
                if i == textLevel:
                    if abs(v) < .001 or abs(v) >= 10000:
                        vstr = "%g" % (v * self.scale)
                    else:
                        vstr = ("%%0.%df" % places) % (v * self.scale)
                        
                    textRect = p.boundingRect(QtCore.QRectF(0, 0, 100, 100), QtCore.Qt.AlignCenter, vstr)
                    height = textRect.height()
                    self.textHeight = height
                    if self.orientation == 'left':
                        textFlags = QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStop-100, x-(height/2), 99-max(0,self.tickLength), height)
                    elif self.orientation == 'right':
                        textFlags = QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter
                        rect = QtCore.QRectF(tickStop+max(0,self.tickLength)+1, x-(height/2), 100-max(0,self.tickLength), height)
                    elif self.orientation == 'top':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignBottom
                        rect = QtCore.QRectF(x-100, tickStop-max(0,self.tickLength)-height, 200, height)
                    elif self.orientation == 'bottom':
                        textFlags = QtCore.Qt.AlignCenter|QtCore.Qt.AlignTop
                        rect = QtCore.QRectF(x-100, tickStop+max(0,self.tickLength), 200, height)
                    
                    p.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
                    #p.drawText(rect, textFlags, vstr)
                    texts.append((rect, textFlags, vstr))
                    
        prof.mark('draw ticks')
        for args in texts:
            p.drawText(*args)
        prof.mark('draw text')
        prof.finish()
        
    def show(self):
        
        if self.orientation in ['left', 'right']:
            self.setWidth()
        else:
            self.setHeight()
        GraphicsWidget.show(self)
        
    def hide(self):
        if self.orientation in ['left', 'right']:
            self.setWidth(0)
        else:
            self.setHeight(0)
        GraphicsWidget.hide(self)

    def wheelEvent(self, ev):
        if self.linkedView is None or self.linkedView() is None: return
        if self.orientation in ['left', 'right']:
            self.linkedView().wheelEvent(ev, axis=1)
        else:
            self.linkedView().wheelEvent(ev, axis=0)
        ev.accept()
