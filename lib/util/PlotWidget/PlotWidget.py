# -*- coding: utf-8 -*-
from PyQt4 import Qwt5 as Qwt
from PyQt4 import QtCore, QtGui, QtSvg
from lib.util.MetaArray import MetaArray
from numpy import *
from plotConfigTemplate import Ui_Form

class PlotWidget(Qwt.QwtPlot):
    def __init__(self, *args):
        Qwt.QwtPlot.__init__(self, *args)
        self.setMinimumHeight(50)
        self.setCanvasBackground(QtGui.QColor(0,0,0))
        self.setAxisFont(self.yLeft, QtGui.QFont("Arial", 7))
        self.setAxisFont(self.xBottom, QtGui.QFont("Arial", 7))
        #self.zoomer = Qwt.QwtPlotZoomer(
            #Qwt.QwtPlot.xBottom,
            #Qwt.QwtPlot.yLeft,
            #Qwt.QwtPicker.DragSelection,
            #Qwt.QwtPicker.AlwaysOff,
            #self.canvas())
        self.plotLayout().setCanvasMargin(0)
        #self.zoomer.setRubberBandPen(QtGui.QPen(QtGui.QColor(250, 250, 200)))
        
        self.curves = []
        self.paramIndex = {}
        self.avgCurves = {}
        
        ### Set up context menu
        
        w = QtGui.QWidget()
        self.ctrl = c = Ui_Form()
        c.setupUi(w)
        dv = QtGui.QDoubleValidator(self)
        self.ctrlMenu = QtGui.QMenu()
        ac = QtGui.QWidgetAction(self)
        ac.setDefaultWidget(w)
        self.ctrlMenu.addAction(ac)
        
        c.xMinText.setValidator(dv)
        c.yMinText.setValidator(dv)
        c.xMaxText.setValidator(dv)
        c.yMaxText.setValidator(dv)
        
        QtCore.QObject.connect(c.xMinText, QtCore.SIGNAL('editingFinished()'), self.updateManualXScale)
        QtCore.QObject.connect(c.xMaxText, QtCore.SIGNAL('editingFinished()'), self.updateManualXScale)
        QtCore.QObject.connect(c.yMinText, QtCore.SIGNAL('editingFinished()'), self.updateManualYScale)
        QtCore.QObject.connect(c.yMaxText, QtCore.SIGNAL('editingFinished()'), self.updateManualYScale)
        
        QtCore.QObject.connect(c.xManualRadio, QtCore.SIGNAL('toggled(bool)'), self.updateXScale)
        QtCore.QObject.connect(c.yManualRadio, QtCore.SIGNAL('toggled(bool)'), self.updateYScale)
        
        QtCore.QObject.connect(c.xAutoRadio, QtCore.SIGNAL('clicked()'), self.updateXScale)
        QtCore.QObject.connect(c.yAutoRadio, QtCore.SIGNAL('clicked()'), self.updateYScale)
        
        
        
        
        
        
        
        
        self.replot()
        
    def updateXScale(self, b=False):
        if b:
            self.updateManualXScale()
        else:
            self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
            self.replot()
        
    def updateYScale(self, b=False):
        if b:
            self.updateManualYScale()
        else:
            self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
            self.replot()
        
        
    def updateManualXScale(self):
        x1 = float(self.ctrl.xMinText.text())
        x2 = float(self.ctrl.xMaxText.text())
        self.ctrl.xManualRadio.setChecked(True)
        self.setXRange(x1, x2)
        self.replot()
        
    def updateManualYScale(self):
        y1 = float(self.ctrl.yMinText.text())
        y2 = float(self.ctrl.yMaxText.text())
        self.ctrl.yManualRadio.setChecked(True)
        self.setYRange(y1, y2)
        self.replot()
        
    def plotRange(self):
        xsd = self.axisScaleDiv(self.xBottom)
        ysd = self.axisScaleDiv(self.yLeft)
        ## Silly API change
        if not hasattr(xsd, 'lowerBound'):
            xsd.lowerBound = xsd.lBound
            xsd.upperBound = xsd.hBound
            ysd.lowerBound = ysd.lBound
            ysd.upperBound = ysd.hBound
        return ((xsd.lowerBound(), xsd.upperBound()), (ysd.lowerBound(), ysd.upperBound()))
        
    def screenScale(self):
        mx = self.axisScaleDraw(self.xBottom).map()
        my = self.axisScaleDraw(self.yLeft).map()
        return array([mx.transform(1.0) - mx.transform(0.0), my.transform(1.0) - my.transform(0.0)], dtype=float)
        
    def scaleBy(self, s):
        xr, yr = self.plotRange()
        xd = (xr[1] - xr[0]) * s[0] * 0.5
        yd = (yr[1] - yr[0]) * s[1] * 0.5
        xc = (xr[1] + xr[0]) * 0.5
        yc = (yr[1] + yr[0]) * 0.5
        #print s, xr, xd, yr, yd
        
        self.setXRange(xc - xd, xc + xd)
        self.setYRange(yc - yd, yc + yd)
        self.replot()
        
    def translateBy(self, t, screen=False):
        t = t.astype(float)
        if screen:  ## scale from pixels
            t /= self.screenScale()
        xr, yr = self.plotRange()
        self.setAxisScale(self.xBottom, xr[0] + t[0], xr[1] + t[0])
        self.setAxisScale(self.yLeft, yr[0] + t[1], yr[1] + t[1])
        self.replot()
        
        
    def mouseMoveEvent(self, ev):
        pos = array([ev.pos().x(), ev.pos().y()])
        dif = pos - self.mousePos
        self.mousePos = pos
        
        ## Ignore axes if mouse is disabled
        mask = array([1, 1])
        if not self.ctrl.xMouseCheck.isChecked():
            mask[0] = 0
        if not self.ctrl.yMouseCheck.isChecked():
            mask[1] = 0
        
        ## Scale or translate based on mouse button
        if ev.buttons() & QtCore.Qt.LeftButton:
            self.translateBy(-dif * mask, screen=True)
        elif ev.buttons() & QtCore.Qt.RightButton:
            dif[0] *= -1
            s = ((mask * 0.02) + 1) ** dif
            self.scaleBy(s)
            
        Qwt.QwtPlot.mouseMoveEvent(self, ev)
        
    def mousePressEvent(self, ev):
        self.mousePos = array([ev.pos().x(), ev.pos().y()])
        self.pressPos = self.mousePos.copy()
        Qwt.QwtPlot.mousePressEvent(self, ev)
        
    def mouseReleaseEvent(self, ev):
        pos = array([ev.pos().x(), ev.pos().y()])
        if sum(abs(self.pressPos - pos)) < 3:  ## Detect click
            if ev.button() == QtCore.Qt.RightButton:
                self.ctrlMenu.popup(self.mapToGlobal(ev.pos()))
        self.mousePos = pos
        Qwt.QwtPlot.mouseReleaseEvent(self, ev)
        
    #def clearZoomStack(self):
        #"""Auto scale and clear the zoom stack"""
        #self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
        #self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
        #self.replot()
        #self.zoomer.setZoomBase()

    def plot(self, data, x=None, clear=True, params=None):
        if clear:
            self.clear()
        
        if isinstance(data, MetaArray):
            ids = self.plotMetaArray(data)
        elif isinstance(data, ndarray):
            ids = self.plotArray(data, x=x)
        elif isinstance(data, list):
            if x is not None:
                x = array(x)
            ids = self.plotArray(array(data), x=x)
        else:
            raise Exception('Not sure how to plot object of type %s' % type(data))
            
            
        
            
            
        self.replot()
        
        self.indexParams(params, ids)
        
        return ids
        
    def indexParams(self, params, ids):
        """Add IDs into the parameter index for params"""
        pass
        

    def autoRange(self):
        if self.ctrl.xAutoRadio.isChecked():
            self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
        if self.ctrl.yAutoRadio.isChecked():
            self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
            
    
        r = self.plotRange()
        
        if self.ctrl.xAutoRadio.isChecked():
            self.ctrl.xMinText.setText('%g' % r[0][0])
            self.ctrl.xMaxText.setText('%g' % r[0][1])
        if self.ctrl.yAutoRadio.isChecked():
            self.ctrl.yMinText.setText('%g' % r[1][0])
            self.ctrl.yMaxText.setText('%g' % r[1][1])
            
        w = self.size().width()
        for c in self.curves:
            c.setDisplayRange(r[0][0], r[0][1], w)

    def setAxisTitle(self, axis, title):
        text = Qwt.QwtText(title)
        text.setFont(QtGui.QFont('Arial', 8))
        Qwt.QwtPlot.setAxisTitle(self, axis, text)
        
    def plotArray(self, arr, x=None):
        arr = atleast_2d(arr)
        if arr.ndim != 2:
            raise Exception("Array must be 1 or 2D to plot (shape is %s)" % arr.shape)
            
        if x is None:
            x = arange(arr.shape[1])
            
        x = atleast_2d(x)
        if x.ndim != 2:
            raise Exception("X array must be 1 or 2D to plot (shape is %s)" % x.shape)
            
        
        ret = []
        for i in range(arr.shape[0]):
            c = PlotCurve()
            c.setData(x[i%x.shape[0]], arr[i])
            c.attach(self)
            ret.append(len(self.curves))
            #self.curves.append(c)
                
        self.replot()
        return ret
            
        
        
    def plotMetaArray(self, arr):
        inf = arr.infoCopy()
        
        if arr.ndim == 1:
            xAxis = 0
            yAxis = 1
            
        elif arr.ndim == 2:
            for i in [0,1]:
                if 'cols' in inf[i]:
                    xAxis = 1-i
                    yAxis = i
        else:
            raise Exception('can only automatically plot 1 or 2 dimensional arrays.')
                    
        titles = ['', '']
        for i in [1,0]:
            t = ''
            if i >= len(inf):
                continue
            
            ## If there are columns, pick title/units from first column
            if 'cols' in inf[i]:
                s = inf[i]['cols'][0]
            else:
                s = inf[i]
                
            if 'name' in s:
                t = s['name']
            if 'units' in s:
                t += ' (%s)' % s['units']
            
        ## Set axis titles
        titles = ['', '']
        for i in [0,1]:
            if 'name' in inf[i]:
                titles[i] = inf[i]['name']
            if 'units' in inf[i]:
                titles[i] = titles[i] + ' (%s)' % inf[i]['units']
        self.setAxisTitle(self.xBottom, titles[0])
        self.setAxisTitle(self.yLeft, titles[1])

        ## create curves
        #curves = []
        try:
            xv = arr.xvals(xAxis)
        except:
            print "Making up xvals"
            print arr
            raise
            xv = range(arr.shape[xAxis])
            
        ret = []
        if arr.ndim == 2:
            for i in range(arr.shape[yAxis]):
                c = PlotCurve()
                c.setData(xv, arr[yAxis:i])
                #c.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
                c.attach(self)
                ret.append(len(self.curves))
                #self.curves.append(c)
        else:
            c = PlotCurve()
            c.setData(xv, arr)
            #c.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            c.attach(self)
            ret.append(len(self.curves))
            #self.curves.append(c)
            
            
        self.replot()
        return ret

    def writeSvg(self, fileName=None):
        if fileName is None:
            fileName = str(QtGui.QFileDialog.getSaveFileName())
        self.svg = QtSvg.QSvgGenerator()
        self.svg.setFileName(fileName)
        self.svg.setSize(self.size())
        self.svg.setResolution(600)
        painter = QtGui.QPainter(self.svg)
        self.print_(painter, self.rect())
        
    def writeImage(self, fileName=None):
        if fileName is None:
            fileName = str(QtGui.QFileDialog.getSaveFileName())
        self.png = QtGui.QImage(self.size(), QtGui.QImage.Format_ARGB32)
        painter = QtGui.QPainter(self.png)
        #rh = self.renderHints()
        #self.setRenderHints(QtGui.QPainter.Antialiasing)
        self.print_(painter, self.rect())
        #self.setRenderHints(rh)
        self.png.save(fileName)
        
    def setYRange(self, min, max):
        self.setAxisScale(self.yLeft, min, max)
        self.ctrl.yMinText.setText('%g' % min)
        self.ctrl.yMaxText.setText('%g' % max)
        
    def setXRange(self, min, max):
        self.setAxisScale(self.xBottom, min, max)
        self.ctrl.xMinText.setText('%g' % min)
        self.ctrl.xMaxText.setText('%g' % max)

    def replot(self):
        Qwt.QwtPlot.replot(self)
        self.autoRange()
        
    def clear(self):
        Qwt.QwtPlot.clear(self)
        self.curves = []
        self.paramIndex = {}

    def registerCurve(self, curve):
        self.curves.append(curve)

    def unregisterCurve(self, curve):
        self.curves.remove(curve)
        
                
    
class PlotCurve:
    """Reimplements QwtPlotCurve to include automatic decimation, alpha, and point display.
    Assumes X values are linear/ascending.
    """
    def __init__(self, *args):
        self.xData = None
        self.yData = None
        self.currentCurve = None
        self.plot = None
        self.pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
    
    def setData(self, x, y):
        self.xData = x
        self.yData = y
        self.generateCurves()
        
    def setDisplayRange(self, min, max, width):
        if self.xData is None or len(self.xData) < 2:
            return
        dif = max-min
        dx = (self.xData[-1] - self.xData[0]) / (len(self.xData) - 1)
        numPts = dif / dx
        
        if numPts < width:
            ptAlpha = 255 * clip(0.1 * width/numPts, 0, 1)
            alpha = 255
            showPts = True
        else:
            ptAlpha = 0
            showPts = False
            alpha = clip(255 * width / numPts, 1, 255)
        cc = 0
        self.setCurve(cc)
        s = Qwt.QwtSymbol(
            Qwt.QwtSymbol.Ellipse, 
            QtGui.QBrush(), 
            QtGui.QPen(QtGui.QColor(200,200,255,ptAlpha)), 
            QtCore.QSize(5,5))
        if showPts:
            self.curves[cc].setSymbol(s)
            self.curves[cc].setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, alpha)))
        else:
            s.setStyle(Qwt.QwtSymbol.NoSymbol)
            self.curves[cc].setSymbol(s)
            self.curves[cc].setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, alpha)))
            
            
        
        
    def attach(self, plot):
        self.plot = plot
        if self.currentCurve is not None:
            self.curves[self.currentCurve].attach(plot)
            #print "attach", self.curves[self.currentCurve]
        if hasattr(plot, 'registerCurve'):
            plot.registerCurve(self)
            
        
    def generateCurves(self):
        plot = self.plot
        self.detach()
        self.curves = []
        self.curves.append(Qwt.QwtPlotCurve())
        self.curves[-1].setPen(self.pen)
        #print "new plot", self.curves[-1]
        self.curves[-1].setData(self.xData, self.yData)
        self.currentCurve = 0
        if plot is not None:
            self.attach(plot)
    
    def detach(self):
        if self.currentCurve is not None:
            self.curves[self.currentCurve].detach()
            #print "detach", self.curves[self.currentCurve]
            if hasattr(self.plot, 'unregisterCurve'):
                self.plot.unregisterCurve(self)
        self.plot = None
            
    def setCurve(self, c):
        if c == self.currentCurve:
            return
        plot = self.plot
        self.detach()
        self.currentCurve = c
        self.curves[c].setPen(self.pen)
        self.attach(plot)
    
    def setPen(self, pen):
        self.pen = pen
        if self.currentCurve is not None:
            self.curves[self.currentCurve].setPen(pen)
    
    