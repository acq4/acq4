# -*- coding: utf-8 -*-
import PyQt4.Qwt5 as Qwt
from PyQt4 import QtCore, QtGui

class PlotWidget(Qwt.QwtPlot):
    def __init__(self, *args):
        Qwt.QwtPlot.__init__(self, *args)
        self.setMinimumHeight(50)
        self.setCanvasBackground(QtGui.QColor(0,0,0))
        self.setAxisFont(self.yLeft, QtGui.QFont("Arial", 7))
        self.setAxisFont(self.xBottom, QtGui.QFont("Arial", 7))
        self.zoomer = Qwt.QwtPlotZoomer(
            Qwt.QwtPlot.xBottom,
            Qwt.QwtPlot.yLeft,
            Qwt.QwtPicker.DragSelection,
            Qwt.QwtPicker.AlwaysOff,
            self.canvas())
        self.plotLayout().setCanvasMargin(0)
        self.zoomer.setRubberBandPen(QtGui.QPen(QtGui.QColor(250, 250, 200)))
        self.replot()
        
        
    def clearZoomStack(self):
        """Auto scale and clear the zoom stack"""
        self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
        self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
        self.replot()
        self.zoomer.setZoomBase()

    def plot(self):
        self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
        self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
        self.replot()
        self.zoomer.setZoomBase()

    def setAxisTitle(self, axis, title):
        text = Qwt.QwtText(title)
        text.setFont(QtGui.QFont('Arial', 8))
        Qwt.QwtPlot.setAxisTitle(self, axis, text)
        
    def plotMetaArray(self, arr):
        self.clear()
        inf = arr.infoCopy()
        
        if arr.ndim == 1:
            xAxis = 0
            yAxis = 1
            
            
        elif arr.ndim == 2:
            for i in [0,1]:
                if 'cols' in inf[i]:
                    xAxis = 1-i
                    yAxis = i
                    
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
            
            
        else:
            raise Exception('can only automatically plot 1 or 2 dimensional arrays.')
        

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
        curves = []
        for i in range(arr.shape[1]):
            c = Qwt.QwtPlotCurve()
            c.setData(arr.xvals(0), arr[:, i])
            c.attach(self)
            
        self.plot()

        