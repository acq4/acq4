#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python class Wrapper for Qwt library for simple plots.
Includes the following methods:
PlotClear clears the selected plat
PlotLine is a matlab-like plotting routine for drawing lines, with
optional symbols, colors, etc. This is only to access the most common
plotting attributes for simple data plots, by mapping from the Qwt names
to the matlab names. 
"""
# January, 2009
# Paul B. Manis, Ph.D.
# UNC Chapel Hill
# Department of Otolaryngology/Head and Neck Surgery
# Supported by NIH Grants DC000425-22 and DC004551-07 to PBM.
# Copyright Paul Manis, 2009
#
"""
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
"""
    Additional Terms:
    The author(s) would appreciate that any modifications to this program, or
    corrections of erros, be reported to the principal author, Paul M
    
    Note: This program also relies on the TrollTech Qt libraries for the GUI.anis, at
    pmanis@med.unc.edu, with the subject line "PySounds Modifications". 
    You must obtain these libraries from TrollTech directly, under their license
    to use the program.
"""

import sys, os, re
from PyQt4 import Qt, QtCore, QtGui
import PyQt4.Qwt5 as Qwt
from PyQt4.Qwt5.anynumpy import *
import sip
from sets import *
import ctypes
import urllib

import time

if os.name is not 'nt':
    import appscript # support applescript talk to Igor etc.
    from grace import GracePlotter
else:
    import win32com.client # allow active x talk to Igor etc.


class WtPlot(QwtPlot):
    def __init__(self):
        QwtPlot.__init__(self)
        #self.setAxisFont(...)
        self.zoomer = Qwt.QwtPlotZoomer(
            Qwt.QwtPlot.xBottom,
            Qwt.QwtPlot.yLeft,
            Qwt.QwtPicker.DragSelection,
            Qwt.QwtPicker.AlwaysOff,
            self.plot.canvas())
        self.zoomer.setRubberBandPen(Qt.QPen(Qt.Qt.black))
        
class MPlot:
    
    def __init__(self):
#        print 'loading MPlot from PyLibrary'
        self.__makeTables()

        self.igorIndex = 0
        self.graceIndex = 1  # constants to index the above dictionaries
        
        self.defaultBkColor = Qt.Qt.white
        self.deselectPen = Qt.QPen(Qt.QColor(232, 232, 232))
        self.deselectColor = Qt.QColor(232,232,232) # color for symbols is different

        self.xlabel = None
        self.ylabel = None
        self.plotList = [] # keep track of plots on the screen
        self.CurrentPlot = [] # keep track of where the mouse is currently located
        self.LastClickedPlot = [] # and the last one we did something in
        self.mainWindow = [] # these need to be set before we can use the export routines
        self.mainUi = []
        self.linkTable={}

#------------------------------- Common User-called Routines ---------------------------

    def PlotReset(self, plot, bkcolor=None, mouse=True, zoom=True, xlabel=None, ylabel=None,
                                 xscale = 'linear', yscale = 'linear' , textName=None,
                                 unitsX = None, unitsY = None,
                                 gridX = False, gridY = False,
                                 linemode = 'lines',
                                 title=None,
                                 xAxisOn = True, yAxisOn = True,
                                 xMinorTicks=None, yMinorTicks=None,
                                 xMajorTicks=None, yMajorTicks=None,
                                 xExtent = None, yExtent = "-1000.0",
                                 clearFlag = True, legend = None):
        """ PlotReset clears the plot data and sets some of the basics about the plot:
         clearFlag : set to False to change selected plot parameters without clearing everything.
         plot      : the plot object that we will modify
         title     : title to place above the graph
         bkcolor   : the background color (a Qt color)
         mouse     : set False to disable mouse tracking over the plot (see way below for mouse handling)
         zoom       : set False to disallow zooming (default: True)
         xlabel, ylabel  : The text labels for the x and y axes (string)
         unitsX, unitsY  : appended to the text labels for the units (string)
         xscale, yscale  : linear or log scaling for the axes (default 'linear')
         textName=None : a text name that can be used to find the axis in a list.
         gridX, gridY : enable the grid by setting True (default False)
         linemode = 'lines',
         xAxisOn, yAxisOn : set False to disable plotting axes and ticks
         xMinorTicks=None, yMinorTicks=None : set to a number to control major and minor ticks
         xMajorTicks=None, yMajorTicks=None,
         xExtent = None, yExtent = "-1000.0" : set to a value of the largest string
         that we might need to show (helps keep plots aligned when multiple are on the page)
        """
        if plot not in self.plotList:
            self.plotList.append(plot) # keep track of the plots 
        if clearFlag: # usually we need to do this, but sometimes we just want to adjust the plot
            plot.clear()
            plot.selectState = 0 # reset our selection state: 0 is none, 1 is some, 2 is all
            plot.plotDict={}
            plot.plotCount = 0
            plot.MouseLastPos = []
            plot.MTimesX=[0.0,0.0]
            plot.MTimesY=[0.0,0.0]
            plot.data = [] # plot has no data in it.
            plot.nPoints = 0 # reset number of points stored in the mouse
            plot.setAxisLabelAlignment(Qwt.QwtPlot.yLeft, Qt.Qt.AlignLeft)
            plot.plotLayout().setAlignCanvasToScales(False)    
            fm = plot.axisWidget(Qwt.QwtPlot.yLeft).fontMetrics() # get current font metrics
            sd = plot.axisScaleDraw(Qwt.QwtPlot.yLeft) # get the scale draw info
            sd.setMinimumExtent(fm.width(yExtent)) # now set the extent to fit our selected number
        if title is not None: # set the title and make it less gaudy than the default
            titl = Qwt.QwtText()
            titl.setFont(Qt.QFont('Arial', 12, Qt.QFont.Normal))
            titl.setText(title)
            plot.setTitle(titl)
        plot.unitsX=unitsX
        plot.unitsY=unitsY
        if textName is not "_keep_":
            plot.textualName = textName
        plot.linemode = linemode
        if bkcolor != None:
            plot.setCanvasBackground(self.__getColor(bkcolor))
        else:
            plot.setCanvasBackground(self.defaultBkColor)
        if gridX or gridY: # grid on X and/or Y
            self.grid = Qwt.QwtPlotGrid()
            self.grid.enableXMin(False)
            self.grid.enableYMin(False)
            self.grid.setMajPen(Qt.QPen(Qt.Qt.darkGray, 0, Qt.Qt.DotLine))
            self.grid.setMinPen(Qt.QPen(Qt.Qt.darkGray, 0, Qt.Qt.DotLine))
            if gridX:
                self.grid.enableX(True)
            if gridY:
                self.grid.enableY(True)
            self.grid.attach(plot)
        if xlabel != None and unitsX != None:
            plot.setAxisTitle(Qwt.QwtPlot.xBottom, ('%s (%s)' % (xlabel, unitsX)))
        if xlabel != None and (unitsX == None or unitsX == ""):
            plot.setAxisTitle(Qwt.QwtPlot.xBottom, ('%s' % (xlabel)))
        if ylabel != None and unitsY!= None:
            plot.setAxisTitle(Qwt.QwtPlot.yLeft, ('%s (%s)' % (ylabel, unitsY)))
        if ylabel != None and (unitsY== None or unitsY == ""):
            plot.setAxisTitle(Qwt.QwtPlot.yLeft, ('%s' % (ylabel)))
        if xscale == 'log10':
            plot.setAxisScaleEngine(Qwt.QwtPlot.xBottom, Qwt.QwtLog10ScaleEngine())
        if yscale == 'log10':
            plot.setAxisScaleEngine(Qwt.QwtPlot.yLeft, Qwt.QwtLog10ScaleEngine())
        if xscale == 'linear':
            plot.setAxisScaleEngine(Qwt.QwtPlot.xBottom, Qwt.QwtLinearScaleEngine())
        if yscale == 'linear':
            plot.setAxisScaleEngine(Qwt.QwtPlot.yLeft, Qwt.QwtLinearScaleEngine())
        if not xAxisOn:
            plot.enableAxis(Qwt.QwtPlot.xBottom, False)
        if not yAxisOn:
            plot.enableAxis(Qwt.QwtPlot.yLeft, False)
        if xMinorTicks is not None:
            plot.setAxisMaxMinor(Qwt.QwtPlot.xBottom, xMinorTicks)
        if yMinorTicks is not None:
            plot.setAxisMaxMinor(Qwt.QwtPlot.yLeft, yMinorTicks)
        if xMajorTicks is not None:
            plot.setAxisMaxMajor(Qwt.QwtPlot.xBottom, xMajorTicks)
        if yMajorTicks is not None:
            plot.setAxisMaxMajor(Qwt.QwtPlot.yLeft, yMajorTicks)
        plot.replot()
        if mouse:
            self.PlotTracking(plot)
        if zoom:
            self.PlotZooming(plot) # attach a zoomer
    
    # display a line in the plot with selected colors, symbols, etc.        
    def PlotLine(self, plot, x, y, color='k', linestyle = '-', linethick=1,
                 symbol=None, symbolsize=9, symbolcolor=None, symbolthick=1,
                 dataID=None, dataShape=None):
        cu = Qwt.QwtPlotCurve() # make a curve instance
        
        lcolor = self.__getColor(color)
        lstyle = self.__getLineStyle(linestyle)
        
        if lstyle is None:
            cu.setStyle(Qwt.QwtPlotCurve.NoCurve)
            cp = Qt.QPen() # default pen
            cp.setColor(lcolor)
            cp.setWidth(0) # no width
        else:
            if plot.linemode == 'lines':
                cu.setStyle(Qwt.QwtPlotCurve.Lines)
            elif plot.linemode == 'sticks':
                cu.setStyle(Qwt.QwtPlotCurve.Sticks)
            elif plot.linemode == 'steps':
                cu.setStyle(Qwt.QwtPlotCurve.Steps)
                cu.setCurveAttribute(Qwt.QwtPlotCurve.Inverted, True)
            elif plot.linemode == 'dots':
                cu.setStyle(Qwt.QwtPlotCurve.Dots)
            else:
                cu.setStyle(Qwt.QwtPlotCurve.Lines)
                
            cp = Qt.QPen(lstyle)
            cp.setColor(lcolor)
            cp.setWidth(linethick)
        cu.setPen(cp)
        cpp={'style':lstyle, 'color': lcolor, 'width': linethick} # store for future ref
        if symbolsize is not None and symbolcolor is None:
            symbolcolor = color
        scolor = self.__getColor(symbolcolor)
        lsymbol = self.__getSymbol(symbol)
        if lsymbol is None:
            cs = Qwt.QwtSymbol(Qwt.QwtSymbol.NoSymbol,
                    Qt.QBrush(scolor, Qt.Qt.SolidPattern),
                    Qt.QPen(scolor, symbolthick),
                    Qt.QSize(int(symbolsize), int(symbolsize)))
        else:
            cs = Qwt.QwtSymbol(lsymbol,
                    Qt.QBrush(scolor, Qt.Qt.SolidPattern),
                    Qt.QPen(scolor, symbolthick),
                    Qt.QSize(int(symbolsize), int(symbolsize)))
        csp={'symbol': lsymbol, 'brushcolor': scolor, 'pencolor': scolor, 'penthick': symbolthick,
            'size':symbolsize}
        cu.setSymbol(cs)
            
        cu.attach(plot) # add curve to the plot
        cu.setData(x, y) # set the data in the curve
# the following attributes are ones that we add to the QwtCurve type for our reference
        cu.selected = True # indicate all plots are selected as default
        cu.dataID = dataID # save the data ID with the curve
        cu.dataShape = dataShape
        cu.my_pen = cpp # save original settings so we can restore visual modifications
        cu.my_Qpen = cp
        cu.my_marker = csp # (symbol)
        cu.my_Qmarker = cs
        cu.dataX = x # store the data - tried using QwtArrayData recovery
        cu.dataY = y # from setData/xData,yData, but stored in c type ,ng
        cu.mother_plot = plot
        plot.plotCount = plot.plotCount + 1 # keeps track of number of actual plots
        plot.plotDict[plot.plotCount] = cu
        cu.plotCount = plot.plotCount
        
        if hasattr(plot, 'zoomer'): # need to make sure zoomer base is correct
            plot.zoomer.setZoomBase() # note - calls pending replot anyway
        else:
            plot.replot()

    # PlotLine()
    
# PlotSpec is for plotting spectrograms
    def PlotSpec(self, plot, freq, xscale, data, dataID=None):
        sp = Qwt.QwtPlotSpectrogram()
        colorMap = Qwt.QwtLinearColorMap(Qt.Qt.darkCyan, Qt.Qt.red)
        colorMap.addColorStop(0.15, Qt.Qt.cyan)
        colorMap.addColorStop(0.40, Qt.Qt.green)
        colorMap.addColorStop(0.75, Qt.Qt.yellow)

        sp.setColorMap(colorMap)
        sd = SpectrogramData()
        sd.loadData(data.T, ymap = freq, xmap = xscale)
        s = shape(data.T)
        fmin = min(freq)
        fmax = max(freq)
        sd.setLimits(0, fmin,  s[1], fmax)
        sp.setData(sd)
        sp.attach(plot)

        rightAxis = plot.axisWidget(Qwt.QwtPlot.yRight)
        rightAxis.setTitle("Intensity")
        rightAxis.setColorBarEnabled(True);
        rightAxis.setColorMap(sp.data().range(),
                              sp.colorMap())
        plot.setAxisScale(Qwt.QwtPlot.yRight, 
                          sp.data().range().minValue(),
                          sp.data().range().maxValue())
        plot.enableAxis(Qwt.QwtPlot.yRight)
#        plot.setAxisScaleEngine(Qwt.QwtPlot.yLeft, Qwt.QwtLog10ScaleEngine())
        plot.setAxisScale(Qwt.QwtPlot.yLeft, fmin, fmax)
        plot.setAxisScale(Qwt.QwtPlot.xBottom, 0, s[1]) # make scale "tight"
        
        plot.plotLayout().setAlignCanvasToScales(True)
        sp.setDisplayMode(Qwt.QwtPlotSpectrogram.ImageMode, True)
        plot.replot()

        sp.selected = False
        sp.dataID = dataID
        if hasattr(plot, 'zoomer'):
            plot.zoomer.setZoomerBase()
        else:
            plot.replot()
    
        # PlotSpec()

    def Erase(self, widget):
        """remove all the children of the current widget - usually to clear out a tabbed
            widget's subplots
            also removes the children of the plots in the widget """
        thiswidget = self.findWidget(widget)
        ch = thiswidget.findChildren(Qwt.QwtPlot)
        for tch in ch:
            self.plotList.remove(tch)        
            sip.delete(tch) # addition 6/8/09 as suggested by LC - seems to work fine.
        return
                
#        
#----------------------- Support for organizing multiple plots on a page -----------
#
    def newPlot(self, widget, possize=(0.1, 0.1, 0.9, 0.9), title = None, legend=None):
        thiswidget = self.findWidget(widget)
        newplot = Qwt.QwtPlot(thiswidget)
        """insert a new QwtPlot canvas in the current widget, at positions x and y, with
        width w and h, which are relative to x(0,1) and y(0,1) in the widget space.
        keep track of the plots that were added
        """
        if title is not None:
            newplot.textualName = title
            titl = Qwt.QwtText()
            titl.setFont(Qt.QFont('Arial', 12, Qt.QFont.Normal))
            titl.setText(str(title))
            newplot.setTitle(titl)
        wsize =  thiswidget.size() # get the bounds of the outer widget
        newplot.setParent(thiswidget) # attach current plot to the parent
        x0 = int(possize[0]*wsize.width())
        y0 = int((1.0-(possize[1]+possize[3]))*wsize.height())
        x1 = int(possize[2]*wsize.width())
        y1 = int(possize[3]*wsize.height()) # scale the widget 
        newplot.setGeometry(x0, y0, x1, y1)
#        if legend is not None:
#            legend = Qwt.QwtPlot()
#            newplot.insertLegend(legend, pos=Qwt.QwtPlot.LeftLegend)
        newplot.show() # visible
        thiswidget.show() # visible
        if newplot not in self.plotList:
            self.plotList.append(newplot) # keep track of the plots 
        return(newplot)
        
    def subPlot(self, widget, rows, cols, index, sptitle=None, legend = None):
        """Insert a subplot (new QwtPlot) into the widget space matrix with automatic position
            much like the matlab subplot command.
        """
        thiswidget = self.findWidget(widget)
        xwid = (1.0/(cols))
        yht = (1.0/(rows))
        xi = index % (cols) # get the row, column index
        yi = floor(index / cols)
        xp = xi*xwid
        yp = 1.0-yht*(1.0+yi)
        pl = self.newPlot(thiswidget, possize=(xp, yp, xwid, yht), title=sptitle, legend=legend)
        return(pl)

    def sameScale(self, plts, xsame = True, ysame = True):
        """ force all the plots in the plot list plts to have the same scale.
        by default, both x and yaxes are scaled, but this can be also be done
        selectively.
        """
        minY = 1.0e6
        maxY = -1.0e6
        minX = 1.0e6
        maxX = -1.0e6
        for p in plts:
            if ysame:
                axisL = p.axisScaleDiv(Qwt.QwtPlot.yLeft)
                if axisL.lBound() < minY:
                    minY = axisL.lBound()
                if axisL.hBound() > maxY:
                    maxY = axisL.hBound()
            if xsame:
                axisB = p.axisScaleDiv(Qwt.QwtPlot.xBottom)
                if axisB.lBound() < minX:
                    minX = axisB.lBound()
                if axisB.hBound() > maxX:
                    maxX = axisB.hBound()
        
        for p in plts:
            if ysame:
                p.setAxisScale(Qwt.QwtPlot.yLeft, minY, maxY)
                p.enableAxis(Qwt.QwtPlot.yLeft, False)
            if xsame:
                p.setAxisScale(Qwt.QwtPlot.xBottom, minX, maxX)
                p.enableAxis(Qwt.QwtPlot.xBottom, False)
        
    def fillTextBox(self, textbox, textlabel=None, font='Helvetica', size=11, wrap=True):
        """ fillTextBox puts the text in textlabel into the text box with a standard font size
        and allows it to wrap """
        if textlabel is not None:
            textbox.setText(textlabel)
            textbox.setWordWrap(wrap)
            textbox.setFont(Qt.QFont(font, 11))
            if textbox not in self.plotList:
                self.plotList.append(textbox) # keep track of the text boxes too


#--------------------------------Utility routines to help us ------------------------
#
    def getSelectedTraces(self, plot):
        """ return the list of traces that are selected in the current plot """
        sellist = []
        for cu in plot.itemList():
            if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID != None:
                if cu.selected:
                    sellist.append(cu.plotCount-1)
        return(sellist)

# method to request the last 2 coordinates clicked on the current graph
# --- this will be called by the user... 
    def getCoordinates(self, last = None):
        x=None
        y=None
        if last is None:
            pl=self.CurrentPlot
        else:
            pl=self.LastClickedPlot
        npts = len(pl.MTimesX)
        if npts == 2:
            x=pl.MTimesX
            y=pl.MTimesY
        if npts < 2 or x[0] == x[1]:
            axisScale = pl.axisScaleDiv(Qwt.QwtPlot.xBottom)
            x=(axisScale.lBound(), axisScale.hBound())
            axisScale = pl.axisScaleDiv(Qwt.QwtPlot.yLeft)
            y=(axisScale.lBound(), axisScale.hBound())
        return(x,y,pl)
        
#
# -------- More utility routines, but these are not frequently needed to be called by the user, if at all.

    def findWidget(self, widget):
        thiswidget = None
        if not isinstance(widget, Qt.QWidget):
            thiswidget = self.mainUi.findChild(Qt.QWidget, widget) # find from our base plotting class?
        else:
#            print 'widget is %s' % (widget.objectName())
            thiswidget = widget
        return(thiswidget)    

    def deleteChildren(self, p):
        ch = p.findChildren(Qt.QObject)
        for tch in ch:
            del tch
        
    def printChildren(self, p, title='new list'):
        ch =  p.findChildren(Qt.QObject)
        print '\n%s :  ' % (title),
        print p
        for tch in ch:
            print '     child:  ',
            print tch
        
    def getPlotPos(self, plot):
        """ return the location of a graph in the parent widget """
        par = plot.parentWidget()
        found = False
        pargeo = None
        grgeo = None
        thelayout = None
        thegraph = None
        while True:
            wcn = str(par.objectName())
            if par.layout() != 0:
                if thelayout is None:
                    thelayout = par
                    found = True
            if par.isWidgetType() and wcn.startswith('Graph_Tab_'):
                thegraph = par
            par = par.parentWidget() # recurse up to the top
            if par is None:
                break
        if not found:
            return(0.25, 0.25, 0.5, 0.5) # arbitrary 
        geo = plot.geometry() # get our geometry
        laygeo = thelayout.frameGeometry()
        if thegraph is not None:
            grgeo = thegraph.frameGeometry()
        else:
            grgeo = laygeo # assume layout is top
        # compute position in relative frame position
        x0 = (laygeo.x()+geo.x())/float(grgeo.width())
        y0 = (laygeo.y()+geo.y())/float(grgeo.height())
        wid = (geo.width())/float(grgeo.width())
        ht = (geo.height())/float(grgeo.height())
        return((x0, y0, wid, ht))

    def __makeLabel(self, arg, units, braces=None):
        if units == None:
            label = '%.6g' % (arg)
        else:
            if braces == None:
                label = '%.6g %s' % (arg, units)
            else:
                label = '%.6g (%s)' % (arg, units)
                    
        return (label)        
#
#------------Mouse handling support over the graphs --------------
#
    def setXYReport(self, xlabel, ylabel):
        """set the objects that serve as labels for the mouse coordinates."""
        if xlabel != None:
            self.xlabel = xlabel
        else:
            self.xlabel = None
        if ylabel != None:
            self.ylabel = ylabel
        else:
            self.ylabel = None

    def setTReport(self, t0label, t1label, mousewindow=None):
        """set the objects that serve as labels for the Saved mouse coordinates."""
        if t0label != None:
            self.t0label = t0label
        else:
            self.t0label = None
        if t1label != None:
            self.t1label = t1label
        else:
            self.t1label = None
        if mousewindow != None:
            self.mouseWindow = mousewindow
        else:
            self.mouseWindow = None
            
    def setHooks(self, ui):
        self.mainUi = ui
        
    def PlotTracking(self, theplot):
        """Enable tracking of the mouse in the selected plot."""
        if not hasattr(theplot, 'mouseconnect'): # prevent connecting more than once to any plot
            theplot.connect(Spy(theplot.canvas()),
                     Qt.SIGNAL("MouseMove"),
                     self.showCoordinates) # watch the mouse move
            theplot.connect(Spy(theplot.canvas()),
                           Qt.SIGNAL("MouseButtonPress"),
                           self.saveCoordinates) # save coordinates at button presses
            theplot.connect(Spy(theplot.canvas()),
                           Qt.SIGNAL("MouseButtonDblClick"),
                           self.selectOneTrace) # save coordinates at button presses
            theplot.connect(Spy(theplot.canvas()),
                           Qt.SIGNAL("KeyPress"),
                           self.selectMultipleTraces) # save coordinates at button presses
            theplot.mouseconnect = 1
            
    def __Selected(self, curve):
        """ cause a curve to be selected.
        The selection list can be used for fitting, etc.
        """
        curve.setPen(curve.my_Qpen)
        curve.setSymbol(curve.my_Qmarker)
        curve.setZ(0.0) # bring selection to the front
        curve.selected = True # add selection to our list
        if self.linkTable.has_key(curve.mother_plot): # see if we have linked stuff
            p2 = self.linkTable[curve.mother_plot] # get linked plot
            if curve.plotCount in p2.plotDict: # .has_key(curve.plotCount):
                curve2 = p2.plotDict[curve.plotCount] # this is the linked curve
                curve2.setPen(curve2.my_Qpen)
                curve2.setSymbol(curve2.my_Qmarker)
                curve2.setZ(0.0) # bring selection to the front
                curve2.selected = True # add selection to our list
                p2.replot() # force replot of linked plot as well

    def __deSelect(self, curve):
        """ cause a curve to be deselected. The selection can be used for
        fitting, etc."""
        curve.setPen(self.deselectPen)
        sym = curve.symbol()
        curve.setSymbol(Qwt.QwtSymbol(sym.style(), # keep symbol and size, just hide colors
                    Qt.QBrush(self.deselectColor, Qt.Qt.SolidPattern),
                    Qt.QPen(self.deselectColor),
                    Qt.QSize(sym.size())))
        curve.selected = False
        curve.setZ(-1)
        if self.linkTable.has_key(curve.mother_plot): # see if we have linked stuff
            p2 = self.linkTable[curve.mother_plot] # get linked plot
            if curve.plotCount in p2.plotDict: # p2.plotCount.has_key(curve.plotCount):
                curve2 = p2.plotDict[curve.plotCount] # this is the linked curve
                curve2.setPen(self.deselectPen)
                sym = curve2.symbol()
                curve2.setSymbol(Qwt.QwtSymbol(sym.style(), # keep symbol and size, just hide colors
                            Qt.QBrush(self.deselectColor, Qt.Qt.SolidPattern),
                            Qt.QPen(self.deselectColor),
                            Qt.QSize(sym.size())))
                curve2.selected = False
                curve2.setZ(-1)
                p2.replot()

    def linkSelection(self, taba, tabb):
        self.linkTable[taba] = tabb
        self.linkTable[tabb] = taba # make links both ways
        
    def selectOneTrace(self, thecanvas, event):
        """ find the nearest trace to the cursor, and put it into the "selected"
        state. This could include coloring it if it is "deselected"
        """
        mindist = None
        closest = None
        pl = thecanvas.plot()
        nsel = 0
        for cu in pl.itemList():
            if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID != None:
                dist = cu.closestPoint(event.pos())
                if mindist is None:
                    mindist = dist[1]
                    closest = cu
                else:
                    if dist[1] < mindist:
                        mindist = dist[1]
                        closest = cu
        if closest != None:
            if closest.selected is False: # if not currently selected, set to selected
                self.__Selected(closest)               
            else: #Is currently selected, so change to unselected
                self.__deSelect(closest)
        nsel = 0
        ncu = 0
        for cu in pl.itemList():
            if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID != None:
                ncu = ncu + 1
                if cu.selected:
                    nsel = nsel + 1
        if ncu == nsel:
            pl.selectState = -1 # is all selected
        else:
            pl.selectState = nsel # list the number selected
        pl.replot()
        
    def selectMultipleTraces(self, thecanvas, event):
        """Control A (command A) to select or deselect all the traces. """
        if (event.key() == Qt.Qt.Key_A) and (event.modifiers() & Qt.Qt.ControlModifier): # select EVERYTHING or Nothing
            pl = thecanvas.plot()
            sel = 0
            for cu in pl.itemList():
                if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID != None:
                    if pl.selectState == -1: # all selected - then deselect ALL
                        self.__deSelect(cu)
                        sel = 0
                    else: # none or some (0,positive number) - select ALL
                        self.__Selected(cu)
                        sel = -1
            pl.selectState = sel # we don't change the flag unti we are done
            pl.replot()        
        if (event.key() == Qt.Qt.Key_D) and (event.modifiers() & Qt.Qt.ControlModifier): # Deselect EVERYTHING on the plot
            pl = thecanvas.plot()
            for cu in pl.itemList():
                if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID != None:
                    self.__deSelect(cu)
            pl.selectState = 0 # we don't change the flag until we are done
            pl.replot()        

    def saveCoordinates(self, thecanvas, event):
        """ on mouse clicks with SHIFT key, save the coordinates in an array (save plot also) """
        pl = thecanvas.plot() # the plot from the canvas
        self.LastClickedPlot = pl # save the last clicked plot, regardless
        if event.modifiers() & Qt.Qt.ShiftModifier: # then save the position
            pl = thecanvas.plot() # the plot from the canvas
            pl.MouseLastPos = event.pos() # save the last hit position _always_
            xp = pl.invTransform(Qwt.QwtPlot.xBottom, event.pos().x())
            yp = pl.invTransform(Qwt.QwtPlot.xBottom, event.pos().y())
            if xp == pl.MTimesX[1] and pl.nPoints == 2:
                return # prevent double calls
            if pl.nPoints == 0: # if there are no points, store the first one
                pl.MTimesX[0] = xp
                pl.MTimesY[0] = yp
                pl.nPoints = 1
            elif pl.nPoints == 1:
                pl.MTimesX[1] = xp 
                pl.MTimesY[1] = yp
                pl.nPoints = 2
            elif pl.nPoints == 2:
                pl.MTimesX[0] = pl.MTimesX[1]
                pl.MTimesX[1] = xp
                pl.MTimesY[0] = pl.MTimesY[1]
                pl.MTimesY[1] = yp
            # display the coordinates in the label boxes        
            if pl.nPoints > 0 and self.t0label != None:
                self.t0label.setText(self.__makeLabel(min(pl.MTimesX), pl.unitsX))
                self.t1label.setText(self.__makeLabel(max(pl.MTimesX), pl.unitsY))

    def showCoordinates(self, thecanvas, position):
        """ display the coordinates in the label boxes """
        pl = thecanvas.plot() # the plot from the canvas    
        pl.MouseLastPos = position # save the last hit position _always_
        try:
            if self.xlabel != None:
                self.xlabel.setText(self.makeLabel(
                    pl.invTransform(Qwt.QwtPlot.xBottom, position.x()), pl.unitsX))
                self.ylabel.setText(self.makeLabel(
                    pl.invTransform(Qwt.QwtPlot.yLeft, position.y()), pl.unitsY))
            if pl != self.CurrentPlot:
                self.CurrentPlot = pl # update info specific to the current plot window
                self.mouseWindow.setText('%s' % (pl.textualName))
                if self.t0label != None:
                    self.t0label.setText(self.makeLabel(min(pl.MTimesX), pl.unitsX))
                    self.t1label.setText(self.makeLabel(max(pl.MTimesX), pl.unitsY))
        except:
            pass # it is possible that pl.units is not set if graph built but not
        # initialized by us

# get clipped curve data between t0 and t1 from the selected QwtCurve
    def getClipCurveData(self, curve, t0, t1):
        x = curve.x
        print x
        dat = curve.data()
        print "what about it?"
        return (0,0)
        
# initiate plot zooming        
    def PlotZooming(self, theplot):
        if not hasattr(theplot, 'zoomer'): # only attach the zoomer to the plot once
            theplot.zoomer = Qwt.QwtPlotZoomer(Qwt.QwtPlot.xBottom,
                                        Qwt.QwtPlot.yLeft,
                                        Qwt.QwtPicker.DragSelection,
                                        Qwt.QwtPicker.AlwaysOff,
                                        theplot.canvas())
            theplot.zoomer.setRubberBandPen(Qt.QPen(Qt.Qt.red))
            theplot.zoomer.initMousePattern(2)
        theplot.setAxisAutoScale(Qwt.QwtPlot.yLeft) # make sure we are autoscaled
        theplot.setAxisAutoScale(Qwt.QwtPlot.xBottom)
        theplot.zoomer.setZoomBase() # make sure we reset the base to be save


#--------------------  Mapping Qt and PyQt and Igor stuff - we use our own tables based on
#  the Qt Tables. User never needs to call these.

    def __makeTables(self):
        """ generate the various tables and mappings we can use to make life more
        convenient, and to allow extensions to be more easily comprehended.
        """
        self.colorMap = {
                         None:    Qt.Qt.black,
                         'black': Qt.Qt.black,
                         'k'    : Qt.Qt.black,
                         'blue' : Qt.Qt.blue,
                         'b'    : Qt.Qt.blue,
                         'green':Qt.Qt.green,
                         'g'    : Qt.Qt.green,
                         'red'  : Qt.Qt.red,
                         'r'    : Qt.Qt.red,
                         'yellow': Qt.Qt.yellow,
                         'y'    : Qt.Qt.yellow,
                         'cyan' : Qt.Qt.cyan,
                         'c'    : Qt.Qt.cyan,
                         'white': Qt.Qt.white,
                         'w'    : Qt.Qt.white,
                         'magenta': Qt.Qt.magenta,
                         'm'    : Qt.Qt.magenta,
                         'lightgray' : Qt.Qt.lightGray,
                         'darkgray'   : Qt.Qt.darkGray,
                         'lightgrey' : Qt.Qt.lightGray, # 'cuz I do it both ways and both are correct
                         'darkgrey'   : Qt.Qt.darkGray,
                         'darkred' : Qt.Qt.darkRed,
                         'darkgreen' : Qt.Qt.darkGreen,
                         'darkblue' : Qt.Qt.darkBlue,
                         'darkcyan' : Qt.Qt.darkCyan,
                         'darkmagenta' : Qt.Qt.darkMagenta,
                         'darkyellow' : Qt.Qt.darkYellow                          
                        }
        
        self.lineStyleMap = {
                            None:       Qt.Qt.NoPen,
                            'NoLine':  Qt.Qt.NoPen,
                            'n':        Qt.Qt.NoPen,
                            'Solid':    Qt.Qt.SolidLine,
                            '_':        Qt.Qt.SolidLine, # underscore
                            '-':        Qt.Qt.SolidLine, # hyphen
                            'Dash':     Qt.Qt.DashLine,
                            '--':       Qt.Qt.DashLine,
                            'Dot':      Qt.Qt.DotLine,
                            '.':        Qt.Qt.DotLine,
                            'DashDot':  Qt.Qt.DashDotLine,
                            '-.':       Qt.Qt.DashDotLine,
                            'DashDotDot': Qt.Qt.DashDotDotLine,
                            '-..':      Qt.Qt.DashDotLine
                        }
        
        self.symbolMap = {
                        None        : Qwt.QwtSymbol.NoSymbol,
                        'Ellipse'   : Qwt.QwtSymbol.Ellipse,    'o' : Qwt.QwtSymbol.Ellipse,
                        'Rect'      : Qwt.QwtSymbol.Rect,       's' : Qwt.QwtSymbol.Rect,
                        'Diamond'   : Qwt.QwtSymbol.Diamond,    'd' : Qwt.QwtSymbol.Diamond,
                        'Triangle'  : Qwt.QwtSymbol.Triangle,   't' : Qwt.QwtSymbol.Triangle,
                        'DTriangle' : Qwt.QwtSymbol.DTriangle,  'v' : Qwt.QwtSymbol.DTriangle,
                        'UTriangle' : Qwt.QwtSymbol.UTriangle,  '^' : Qwt.QwtSymbol.UTriangle,
                        'LTriangle' : Qwt.QwtSymbol.LTriangle,  'l' : Qwt.QwtSymbol.LTriangle,
                        'RTriangle' : Qwt.QwtSymbol.RTriangle,  'r' : Qwt.QwtSymbol.RTriangle,
                        'Cross'     : Qwt.QwtSymbol.Cross,      '+' : Qwt.QwtSymbol.Cross, 
                        'X'         : Qwt.QwtSymbol.XCross,     'x' : Qwt.QwtSymbol.XCross, 
                        'HLine'     : Qwt.QwtSymbol.HLine,      '-' : Qwt.QwtSymbol.HLine,
                        'VLine'     : Qwt.QwtSymbol.VLine,      '|' : Qwt.QwtSymbol.VLine,
                        'Star1'     : Qwt.QwtSymbol.Star1,      '*' : Qwt.QwtSymbol.Star1,
                        'Star2'     : Qwt.QwtSymbol.Star2,      '@' : Qwt.QwtSymbol.Star2,
                        'Hexagon'   : Qwt.QwtSymbol.Hexagon,    'h' : Qwt.QwtSymbol.Hexagon
                        }
        # export color map is a dictionary that maps Qt colors to Igor (map[Qt.color][igorIndex]
        # or xmgrace/grace (map [Qt.color][graceIndex]
        # The same is done for symbols and lines.
        # __LineMapper and __SymbolMapper use these dictionaries to map
        # between the various "renderers". This makes it relatively easy to add
        # other output methods by adding entries to these dictionaries.
        # the color map is for the QPen class using QtCore color 
        self.exportColorMap = {
                None:           [(0,0,0), 1],
                Qt.Qt.black:    [(0,0,0),   1],
                Qt.Qt.blue:     [(0,0,6535), 4],
                Qt.Qt.red:      [(65535,0,0), 2],
                Qt.Qt.green:    [(0,65535,0), 3],
                Qt.Qt.cyan:     [(0,65535,65535), 9],
                Qt.Qt.magenta:  [(65535,0,65535), 10],
                Qt.Qt.white:    [(65535,65535,65535), 0],
                Qt.Qt.yellow:   [(65535,65535,0), 5],
                Qt.Qt.lightGray: [(50000, 50000, 50000),7],
                Qt.Qt.darkGray: [(21000, 21000, 21000), 7],  
                Qt.Qt.darkRed: [(32000, 0, 0), 13], 
                Qt.Qt.darkGreen: [(0, 32000, 0), 15],
                Qt.Qt.darkBlue: [(0, 0, 32000), 12],
                Qt.Qt.darkCyan: [(0, 32000, 32000), 14], 
                Qt.Qt.darkMagenta: [(32000, 0, 32000), 8],
                Qt.Qt.darkYellow: [(32000, 32000, 0), 11]
        }

        self.exportSymbolMap = {
                None:                   [None, 0],
                Qwt.QwtSymbol.NoSymbol: [None, 0],
                Qwt.QwtSymbol.Ellipse:  [19, 1],
                Qwt.QwtSymbol.Rect:     [5, 2],
                Qwt.QwtSymbol.Diamond:  [18, 3],
                Qwt.QwtSymbol.Triangle: [17, 4],
                Qwt.QwtSymbol.DTriangle: [23, 6],
                Qwt.QwtSymbol.UTriangle: [17, 4],
                Qwt.QwtSymbol.LTriangle: [46, 5],
                Qwt.QwtSymbol.RTriangle: [49, 7],
                Qwt.QwtSymbol.Cross:    [0, 8],
                Qwt.QwtSymbol.XCross:    [1, 9],
                Qwt.QwtSymbol.HLine:    [9, 0],
                Qwt.QwtSymbol.VLine:    [10, 0],
                Qwt.QwtSymbol.Star1:    [2, 10],
                Qwt.QwtSymbol.Star2:    [2, 10],
                Qwt.QwtSymbol.Hexagon:   [42, 0]
        }
        self.exportLineMap = {
                None:       [None, 0],
                Qt.Qt.NoPen: [None, 0],
                Qt.Qt.SolidLine: [0, 1],
                Qt.Qt.DashLine: [3, 3],
                Qt.Qt.DotLine: [1, 2],
                Qt.Qt.DashDotLine: [5, 5],
                Qt.Qt.DashDotDotLine: [6, 7]
        }

    #Symbol Mapper from Qwt/Qt to Igor, Grace - uses self.exportSymbolMap    
    # marker is the elements of a QwtSymbol, stored in a dictionary for recall    
    def __SymbolMapper(self, marker, device):
        symbol = marker['symbol'] # get the symbol type - it is an extra step, but ... 
        if self.exportSymbolMap.has_key(symbol):
            sym =  self.exportSymbolMap[symbol][device]
        else:
            sym = self.exportSymbolMap[Qwt.QwtSymbol.NoSymbol][device] # default is no symbol.. 
        symbolBrush = marker['brushcolor'] # get the symbol type - it is an extra step, but ... 
        color = marker['pencolor']
        if self.exportColorMap.has_key(color):
            col = self.exportColorMap[color][device]
        else:
            col = self.exportColorMap[QtCore.Qt.black][device] # default is no symbol..
        return(sym, col)

        # SymbolMapper
    
    #Line Mapper from Qwt/Qt to Igor, Grace - uses self.exportLineMap    
    # line is a elements used to set QPen, saved in a structure with
    # line.style, line.color, line.thickness
    def __LineMapper(self, linePen, device):
        linestyle = linePen['style']
        if self.exportLineMap.has_key(linestyle):
            linesty =  self.exportLineMap[linestyle][device]
        else:
            linesty = self.exportLineMap[Qt.Qt.SolidLine][device] # default is a solid line.. 
        color = linePen['color']
        if self.exportColorMap.has_key(color):
            col = self.exportColorMap[color][device]
        else:
            col = self.exportColorMap[QtCore.Qt.black][device] # default is no symbol..
        return(linesty, col)

        # LineMapper
        
        
# return Qt color from the map given the string 
    def __getColor(self, color):
        qcolor = Qt.Qt.black
        try:
            qcolor = self.colorMap[color]
        except:
            pass # qcolor = self.defaultBkColor
        return(qcolor)

# set the color of all the traces in the selected plot to color
    def __setColor(self, plot, color):
        for cu in plot.itemList():
            if isinstance(cu, Qwt.QwtPlotCurve):
                cu.setPen(self.__getColor(color))

# return the Qt symbol from the map given the string        
    def __getSymbol(self, symbol):
        qsymbol = None
        try:
            qsymbol = self.symbolMap[symbol]
        except:
            pass
        return(qsymbol)
    
    def __getLineStyle(self, linestyle):
        qlinestyle = None
        try:
            qlinestyle = self.lineStyleMap[linestyle]
#            print qlinestyle
        except:
            pass
        return(qlinestyle)
        
    def setDefaultBkColor(self, bkcolor):
        self.defaultBkColor = self.__getColor(bkcolor)
    
    def getPlotList(self): # provide plot list to main program for management
        return(self.plotList)




# ------------ Support for Printing and plotting the graphs in a window of some sort
    
# printGraph does just what it says.Open a printer dialog and dump the graph(s) that
# is (are) in the current plot widget to the printer.
    def printGraph(self, plotwidget):
        printer = Qt.QPrinter(Qt.QPrinter.HighResolution)
        dialog = Qt.QPrintDialog(printer)

        if dialog.exec_():
            pixmap=Qt.QPixmap.grabWidget(plotwidget)
            pixmap.scaledToWidth(5000)
            wimage = Qt.QPixmap.toImage(pixmap)
            painter = Qt.QPainter(printer)
            painter.setRenderHint(Qt.QPainter.Antialiasing)
            rect = painter.viewport()
            size = wimage.size()
            size.scale(rect.size(), Qt.Qt.KeepAspectRatio)
            painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
            painter.setWindow(wimage.rect())
            painter.drawImage(Qt.QPoint(0,0), wimage)
            painter.end()

    def exportPDF(self, plotwidget, fileName = None):
        if fileName is None:
            fileName = Qt.QFileDialog.getSaveFileName(
                None,
                'Export File Name',
                'graph.pdf',
                'PDF Documents (*.pdf)')
            if fileName.isEmpty():
                return
        if fileName is not None:
            printer = Qt.QPrinter()
            printer.setOutputFormat(Qt.QPrinter.PdfFormat)
            printer.setOrientation(Qt.QPrinter.Landscape)
            printer.setOutputFileName(fileName)
            printer.setCreator('MPlots')
            plotwidget.RenderFlag(Qt.QWidget.DrawChildren)
            plotwidget.render(printer)
            
    # exportPDF()

    def exportSVG(self, plotwidget, fileName = None):
        if fileName is None:
            fileName = Qt.QFileDialog.getSaveFileName(
                None,
                'Export File Name',
                'graph.ps',
                'PostScript Documents (*.ps)')
            if fileName.isEmpty():
                return
        if fileName is not None:
            printer = Qt.QPrinter()
            printer.setOutputFormat(Qt.QPrinter.PostScriptFormat)
            printer.setOrientation(Qt.QPrinter.Landscape)
            printer.setOutputFileName(fileName)
            printer.setCreator('MPlots')
            plotwidget.RenderFlag(Qt.QWidget.DrawChildren)
            plotwidget.render(printer)
            
    # exportPostScript
    
# export SVG sends the current graph to an SVG file format.
#
    def exportSVG1(self, plotwidget, fileName = None):
        if fileName is None:
            fileName = Qt.QFileDialog.getSaveFileName(
                None,
                'Export File Name',
                'graph.svg',
                'SVG Documents (*.svg)')
            if fileName.isEmpty():
                return
        if fileName is not None:
            imagesize = Qt.QSize(8000, 10000)
            generator = Qt.QSvgGenerator()
            generator.setFileName(fileName)
            generator.setSize(imagesize)
            plotwidget.RenderFlag(Qt.QWidget.DrawChildren)
            pixmap=Qt.QPixmap.grabWidget(plotwidget)
            pixmap.scaledToWidth(imagesize.width())
            wimage = Qt.QPixmap.toImage(pixmap)
            painter = Qt.QPainter(generator)
            painter.drawImage(Qt.QPoint(0,0), wimage)
            painter.end()

    # exportSVG()

    def exportPNG(self, plotwidget, fileName = None):
        if fileName is None:
            fileName = Qt.QFileDialog.getSaveFileName(
                None,
                'Export File Name',
                'graph.png',
                'PNG Documents (*.png)')
            if fileName.isEmpty():
                return
        if fileName is not None:
            imagesize = Qt.QSize(8000, 10000)
            image = Qt.QImage(imagesize, Qt.QImage.Format_ARGB32)
            a_print_filter = Qwt.QwtPlotPrintFilter()
            a_print_filter.setOptions(Qwt.QwtPlotPrintFilter.PrintAll)
            pixmap=Qt.QPixmap.grabWidget(plotwidget)
            pixmap.scaledToWidth(imagesize.width())
            wimage = Qt.QPixmap.toImage(pixmap)
            wimage.save(fileName, 'PNG')

    def gracePlot(self, currentWidget, lName='datac', pause=0.3):
        """Clone the plot into Grace for very high quality hard copy output.
        Know bug: Grace does not scale the data correctly when Grace cannot
        cannot keep up with gracePlot.  This happens when it takes too long
        to load Grace in memory (exit the Grace process and try again) or
        when 'pause' is too short.
        """
        g = GracePlotter(debug = 0)
        # g('pagesize letter; portrait')
        ngraphs = 0
        texts = []
        texts1 = ''
        texts2=''
        for pl in self.plotList:
            if hasattr(pl, 'setText'):
                texts = str(pl.text())# get the text lines
                t = texts.splitlines()    
                texts1 = t[0]
                s= ' '
                texts2=s.join(t[1:])
        plots =  currentWidget.findChildren(Qwt.QwtPlot)
        ngraphs = len(plots)
        #for pl in topwin.list(lName): # for all the plots on the page
        #    if hasattr(pl, 'textualName'): # skip if we have no name - graph is probably not implemented fully
        #        ngraphs = ngraphs + 1
                
        g('arrange ( %d, 1, .1, .1, .1,ON,ON,ON)' % ngraphs) # build an array of the graphs
        # we position them below. rows, columns, offset, vgap, hgap, 
        gno = 0
        for pl in plots: # topwin.list(lName): # for all the plots in the window that we manage
            tlabel = pl.textualName # str(pl.title().text())
#        for pl in topwin.list(lName): # for all the plots on the page
#            if not hasattr(pl, 'textualName'): # skip if we have no name - graph is probably not implemented fully
#                continue
            plpos = self.getPlotPos(pl)  # normalized plot position we can use...
            #specify which graph on the page
            graph = "g%d" % (gno)
            g('%s on; with %s' % (graph, graph))
            fn = tlabel.replace(" ", "_")
            if gno is 0:
                g('title "%s"; title font 4; title size 0.8' % (texts1))
                g('subtitle "%s"; subtitle font 4; subtitle size .6' % (texts2))
#            print "original coords: %g, %g, %g, %g" % (plpos[0], plpos[1],
#                                                plpos[2], plpos[3])
            # set the plot area for this plot by setting the viewport
            # squeeze the frame size down a little:
            xmin = plpos[0] + 0.15
            xwid = plpos[2] -0.07
            ymin = plpos[1] + 0.05
            yht = plpos[3] - 0.07
            top = 1.0
            
            g('with %s; view %g, %g, %g, %g' % (graph, xmin, 
                        (top-(ymin+yht)), xmin+xwid, (top-ymin)))
            g('frame type 1') # graph frames are all half-open
            g('with string; string on; string loctype view')
            g('string %f, %f' % (xmin, (top-ymin-0.02)))
            g('string font 4; string char size 0.9')
            g('string def "%s"' % (tlabel))
            g('redraw')
            xAxis = Qwt.QwtPlot.xBottom
            yAxis = Qwt.QwtPlot.yLeft
            xPlace = "normal"
            yPlace = "normal"
            # x-axes
            axisScale = pl.axisScaleDiv(xAxis)
            gxmin = axisScale.lBound()
            gxmax = axisScale.hBound()
            majStep = axisScale.ticks(Qwt.QwtScaleDiv.MajorTick)
            minStep = axisScale.ticks(Qwt.QwtScaleDiv.MinorTick)
            majStep = majStep[1]-majStep[0]
            minStep = minStep[1]-minStep[0]
            g('with %s' % (graph))
            g('world xmin %g; world xmax %g' % (gxmin, gxmax))
            g('xaxis label "%s"; xaxis label char size 0.8' %
              (str(pl.axisTitle(xAxis).text())))
            g('xaxis ticklabel font 4;  xaxis ticklabel char size 0.65')
            g('xaxis label font 4')
            g('xaxis label place %s' % xPlace)
            g('xaxis tick place %s' % xPlace)
            g('xaxis ticklabel place %s' % xPlace)
            g('xaxis tick major size 0.5')
            g('xaxis tick minor size 0.25')
            time.sleep(pause)
            if pl.axisScaleEngine(xAxis) is Qwt.QwtLog10ScaleEngine():
                g('xaxes scale Logarithmic')
                g('xaxis tick major 10')
                g('xaxis tick minor ticks 9')
            else:
                g('xaxes scale Normal')
            #  g('xaxis tick major %12.6f; xaxis tick minor %12.6f'
            #    % (majStep, minStep))

            # y-axes
            axisScale = pl.axisScaleDiv(yAxis)
            gymin = axisScale.lBound()
            gymax = axisScale.hBound()
            majStep = axisScale.ticks(Qwt.QwtScaleDiv.MajorTick)
            minStep = axisScale.ticks(Qwt.QwtScaleDiv.MinorTick)
            g('world ymin %g; world ymax %g' % (gymin, gymax))
            g('yaxis label "%s"; yaxis label char size 0.8' %
              str(pl.axisTitle(yAxis).text()))
            g('yaxis label place %s' % yPlace)
            g('yaxis tick place %s' % yPlace)
            g('yaxis ticklabel place %s' % yPlace)
            g('yaxis ticklabel font 4; yaxis ticklabel char size 0.65')
            g('yaxis label font 4')
            g('yaxis tick major size 0.5')
            g('yaxis tick minor size 0.25')
            time.sleep(pause)
            if pl.axisScaleEngine(yAxis) is Qwt.QwtLog10ScaleEngine():
                g('yaxes scale Logarithmic')
                g('yaxis tick major 10')
                g('yaxis tick minor ticks 9')
            else:
                majStep = majStep[1]-majStep[0]
                minStep = minStep[1]-minStep[0]
                g('yaxes scale Normal')
            # curves
            setindex = 0
            for curve in pl.itemList(): # for all the selected curves in the plot
                if not curve.selected:
                    continue
               # g('s%s legend "%s"' % (index, curve.title()))
                (linesty, linecolor) = self.__LineMapper(curve.my_pen, self.graceIndex)
                (symbol, symcolor) = self.__SymbolMapper(curve.my_marker, self.graceIndex)
                if linesty is None: # what, no lines?
                    linesty = 0 # but set "line"
            # line style is set
                if symbol is None: # what, no symbols?
                   symbol = 0 # set officially to none
                if symbol > 0:
                    g('s%s symbol %d;'
                      's%s symbol size 0.4;'
                      's%s symbol fill pattern 1;'
                      's%s symbol color %d'
                      % (setindex, symbol, setindex, setindex, setindex, symcolor))
                g('s%s line color %d' % (setindex, linecolor))
                if linesty == 0:
                    g('s%s line linestyle 0' % (setindex))
                else:
                    g('s%s line linestyle 1' % (setindex))
                g('s%s line linewidth 0.5' % (setindex)) # thinner lines
                for i in range(len(curve.dataX)):
                    g('%s.s%s point %g, %g'
                      % (graph, setindex, curve.dataX[i], curve.dataY[i]))
                setindex = setindex + 1
            gno = gno + 1
            
            # finalize
            g('redraw')
        
    # gracePlot()

    def IgorConnect(self):
        if os.name is not 'nt':
            return(appscript.app("/Applications/Igor Pro Folder/Igor Pro"))
        else:
            return(win32com.client.Dispatch("IgorPro.Application"))

    def IgorCmd(self, igor, cmd):
        if os.name is not 'nt':
            igor.Do_Script(cmd)
        else:
            igor.Execute(cmd)
        
# export a graphtab layout to Igor.
# currentWidget is the current selection from the TabPlotList window maintainer class
#
    def IgorExport(self, currentWidget, lName='datac'): # , lName = 'datac'):
        LoadFileCommand = 'LoadWave/A/W/J/D/N/O/K=0 ' # space is needed at end of command
        # now talk to IGOR
        # http://www.macresearch.org/using_igor_pro_with_python_via_appscript
        igor = self.IgorConnect()
        (disk, self.IgorHome) = self.getWorkingPath()
        igordocs = re.sub('/', ':', disk + self.IgorHome)
        # create a layout with lName or just a new layout
        layoutName = 'IE_' + lName # layout name has a few that can't be used ("Main", for example0)
        self.IgorCmd(igor, 'DoWindow/K %s' % (layoutName))
        layoutRect = [50, 100, 400, 600]
        margins = [1.15, 1.15, 0.8, 0.8]   # 0, 1 are offsets, 2 and 3 are wid/ht scale factors
        self.IgorCmd(igor, 'NewLayout /N=%s /W=(%d,%d,%d,%d)' % (layoutName, layoutRect[0], layoutRect[1],
                                                             layoutRect[2]+layoutRect[0],
                                                             layoutRect[3]+layoutRect[1])) # create the new layout
        pn = 0
        n = 0
        plots =  currentWidget.findChildren(Qwt.QwtPlot)
        for pl in plots: # for all the plot objects in the current widget (window)
            if pl not in self.plotList:
                continue
            tlabel = pl.textualName 
            if tlabel is not None:
                fn = tlabel.replace(" ", "_")
            pName = "%s_Gr_%d" % (lName, pn)
            self.IgorCmd(igor, 'DoWindow /K %s' % pName)
            self.IgorCmd(igor,'Display /N=%s' % pName) # create an Igor graph
            plpos = self.getPlotPos(pl)
            w = int((plpos[2]*margins[2])*layoutRect[2])
            h = int((plpos[3]*margins[3])*layoutRect[3])
            self.IgorCmd(igor,"ModifyGraph width=%d, height=%d"% (w, h,))
            for cu in pl.itemList(): # for all the possible curves in the plot
                if isinstance(cu, Qwt.QwtPlotCurve):
                    self.IgorCmd(igor,"PauseUpdate; Silent 1")
                    dataset = "%s_%d" % (fn, n)
                    self.ExportData(cu.dataX, cu.dataY, dataset, fn)
                    fileToPlot =   '"' + igordocs + ':' + fn+ '.txt' + '"'
                    self.IgorCmd(igor, LoadFileCommand+fileToPlot)
                    self.IgorCmd(igor, "AppendToGraph/Q Y%s vs X%s; DelayUpdate" % (dataset, dataset))
                    ysetname = "Y%s" % (dataset)
                    (symbol, symbolcolor) = self.__SymbolMapper(cu.my_marker, self.igorIndex)
                # set symbols and colors to match what is on the screen
                    (linesty, rgb) = self.__LineMapper(cu.my_pen, self.igorIndex)
                    mode = 0 # assume just lines
                    if linesty is None: # what, no lines?
                        mode = 3 # markers only
                        linesty = 0 # but set "line"
                    else: # line style is set
                        if symbol is None: # what, no symbols?
                            symbol = 0 # set officially to none
                        else: # otherwise, we have both lines and symbols
                            mode = 4 # markers with lines in between
                    self.IgorCmd(igor, "ModifyGraph marker(%s)=%d, mode(%s)=%d, lStyle(%s)=%d; DelayUpdate" % 
                            (ysetname, symbol, ysetname, mode, ysetname, linesty))
                    self.IgorCmd(igor, "ModifyGraph useMrkStrokeRGB(%s)=1, mrkStrokeRGB=(%d,%d,%d); DelayUpdate" % 
                            (ysetname, symbolcolor[0], symbolcolor[1], symbolcolor[2]))
                    self.IgorCmd(igor, "ModifyGraph rgb(%s)=(%d,%d,%d); DelayUpdate" %
                            (ysetname, rgb[0], rgb[1], rgb[2]))
                    self.IgorCmd(igor, 'Label left, "\\Z07%s"; DelayUpdate' %
                                 (self.IgorText(unicode(pl.axisTitle(Qwt.QwtPlot.yLeft).text()))))
                    self.IgorCmd(igor, 'Label bottom, "\\Z07%s"; DelayUpdate' %
                                 (self.IgorText(unicode(pl.axisTitle(Qwt.QwtPlot.xBottom).text()))))
                    # transfer axis scales as well:
                    axisL = pl.axisScaleDiv(Qwt.QwtPlot.yLeft)
                    axisB = pl.axisScaleDiv(Qwt.QwtPlot.xBottom)
                    self.IgorCmd(igor, 'SetAxis bottom %f,%f; DelayUpdate' % (axisB.lBound(), axisB.hBound()))
                    self.IgorCmd(igor, 'SetAxis left %f,%f; DelayUpdate' % (axisL.lBound(), axisL.hBound()))
                    titl = pl.title()
                    if titl is not []:
                        self.IgorCmd(igor, 'TextBox/C/N=text0/F=0/A=MT/X=0.00/Y=0.00/E=2 "%s\t" ' % unicode(titl.text()))
                    self.IgorCmd(igor,"Silent 0")    
                    n = n + 1
            if n > 0:
                pleft = int((plpos[0]*margins[0])*layoutRect[2]) # x plotpos
                ptop = int((plpos[1]*margins[1])*layoutRect[3])
                pright = int((plpos[2]*margins[2])*layoutRect[2])
                pbot = int((plpos[3]*margins[3])*layoutRect[3])
                self.IgorCmd(igor, "AppendLayoutObject /F=0 /T=1 /W=%s graph %s" % (layoutName, pName))
                self.IgorCmd(igor, "ModifyLayout left(%s)=%d, top(%s)=%d, trans(%s)=1"
                             % (pName, pleft, pName, ptop, pName)) # position and make transparent
                self.IgorCmd(igor, "DoUpdate")
                self.IgorCmd(igor, 'DrawText %d, %d, "%s"' % (pleft, ptop, tlabel))
                self.IgorCmd(igor, "DoUpdate")
                pn = pn + 1
            # now get the plot position and scale it into the layout
        return
    # IgorExport
    def IgorText(self, unistring):
        """ convert unicode string to Igor text as best we can """
        igorstring = unistring.replace(u'\u0394', "\F'Symbol'D\F'Arial'") # unicode cap Delta
        igorstring = igorstring.replace('<sub>', '\B') # subscripts
        igorstring = igorstring.replace('</sub>', '\M') # back to normal
        igorstring = igorstring.replace('<sup>', '\S') # superscripts
        igorstring = igorstring.replace('</sup>', '\M') # back to normal
        return(igorstring)
            
#
# export the current data in the display as a text file
#
    def ExportData(self, x, y, header, filename):
        (disk, self.workpath) = self.getWorkingPath()
        outfilename = os.path.join(self.workpath, filename + '.txt')
        p, self.ExportName = os.path.split(outfilename)
        outfile = open(outfilename, 'w')
        if len(x) != len(y):
            Qt.QMessageBox.critical(self, "Critical Error",
                                          "X and Y lengths are not matched")
            return
        outfile.write("X%s \t Y%s\n" % (header, header))
        for k in range(0, len(x)):
            outfile.write("%f \t %f\n" % (x[k], y[k]))
        outfile.close()            
#        self.Status("Exported data to %s%s" % (p, outfilename))

    # ExportData
#
# Get the current working directory, and then point to Igor data directory
# for data transfer  (see way down on pushing plots to Igor)
#
    def getWorkingPath(self):
        if os.name == 'mac' or os.name == 'posix':
            import commands
            (err, diskinfo)= commands.getstatusoutput('disktool -l')
            #rx = re.compile(r"(volName = '){1}([\w+][\s\w]*)'")
            rx = re.compile(r"(Mountpoint = '/', fsType = 'hfs', volName = '){1}([\w+\s]*)'") # root mount point
            m = rx.search(diskinfo)
            diskhome = m.group(2)
            home = os.path.expanduser("~") # first get the working directory
            return (diskhome, os.path.normpath(home + '/Desktop/IgorDocs'))
        if os.name == 'nt':
            #import subprocess
            #diskinfo = subprocess.call('vol', shell=True)
            pipe = os.popen('vol', 'r')
            diskinfo = pipe.read()
            pipe.close()
            rx = re.compile(r"(Volume in drive ){1}([\w+])( is )([\w\s]*)")
            m = rx.search(diskinfo)
            home = os.path.expanduser('~' + '/My Documents/IgorDocs')
            disk = ''
            return (disk, home)
        
    #getWorkingPath
            


#
# Class to help set up spectrogram plots
# Borrowed and modified from spectromgramDemo.py example program.
#
class SpectrogramData(Qwt.QwtRasterData):

    def __init__(self):
        Qwt.QwtRasterData.__init__(self, Qt.QRectF(-1.0, -1., 1.0, 1.0))
        self.data = []
        
# QRectF sets the x and y axis limits

    # __init__()
    def setLimits(self, x0, y0, xw, yh):
        self.setBoundingRect(Qt.QRectF(x0, y0, xw, yh))
    
    def loadData(self, data, ymap = None, xmap = None):
        self.data = data
        self.shape = shape(data)
        self.ymap = ymap
        self.xmap = xmap
        
    def copy(self):
        return self

    # copy()
    
    def range(self):
        return Qwt.QwtDoubleInterval(amin(self.data), amax(self.data));
# range is the full-scale for the scale bar
    # range()

# this is the plot data, but I don't see where it is called.
# x and y are the coordinate points; we find where these are
# in the data by using xmap and ymap
#
    def value(self, x, y):
        ix = where(abs(minimum(self.xmap-x, 1e6)) < 0.05)[0][0]
        iy = where(abs(minimum(self.ymap-y, 1e6)) < 0.05)[0][0]
        if ix < self.shape[0] and iy < self.shape[1]:
            return(self.data[ix, iy])
        else:
            return(0.0)
    # value()
    
#class SpectrogramData

################################################################################    
# The TabPlotList class stores and returns information about the plots
# in a graphtab window.
# this should be invoked for each graph tab, or better, a single variable
# in the caller can be used to refer to the entire graph window.
# The basic structure is a dictionary of 'Graph Names' (they'd better
# be unique then); each element of the dictionary consists of the graph
# name as a key, the graph tab number, and list of plots (QwtPlot entries).
# methods are provided for maintaining the list and returning whole or parts of
# the entries.
class TabPlotList:
    def __init__(self, graph = None, tabNumber = 0):
        self.Graph={}
        if graph is not None:
            self.addGraph(graph, tabNumber)
    
    def addGraph(self, graph, tabNumber):
        self.Graph[graph]=[tabNumber, []]
        
    def appendPlot(self, graph, plot):
        self.Graph[graph][1].append(plot)
        
    def removeGraph(self, graph):
        del self.Graph[graph]
    
    def removePlots(self, graph):
        self.Graph[graph][1] = [] # this JUST initializes the plots list
    
    def updatePlots(self, graph):
        self.removePlots(graph) # clear out existing list
        
    def printList(self):
        for gr in self.glist():
            print "Graph:",
            print gr
            print ' Plots:: ',
            for pl in self.list(gr):
                print "   plot:",
                print dir(pl)
                
# list method is iterable, returns the plots in the current graph window    
    def list(self, graph):
        if self.Graph.has_key(graph):
            for index in range(0,len(self.Graph[graph][1])):
                yield self.Graph[graph][1][index] 

# glist is iterable, returns keys in graph list
    def glist(self):
        for index in self.Graph.keys():
            yield index

    def getTab(self, graph): # only return the tab associated with the graph
        if self.Graph.has_key(graph):
            return(self.Graph[graph][0])
        else:
            print "key \"%s\" is not in Graph table" % (graph)
            return (-1)
    
    def setTab(self, tabPtr, graph):
        if self.Graph.has_key(graph):
            tabPtr.setCurrentIndex(self.Graph[graph][0]) # select our tab# get parameters form the gui
        else:
            print "key \"%s\" is not in Graph table" % (graph)
            return (-1)

    def getGraphKeyAtTab(self, tabno):
        for index in self.Graph.keys():
            if self.Graph[index][0] == tabno:
                return index
        return [] # nothing if not found
        
    def getPlots(self, graph):
        if self.Graph.has_key(graph):
            return self.Graph[graph][1]
        else:
            print "key \"%s\" is not in Graph table" % (graph)
            return []
            

################################################################################
# spy class captures mouse actions in our plot windows and passes them
# to the handlers.
class Spy(Qt.QObject):
    
    def __init__(self, parent):
        Qt.QObject.__init__(self, parent)
        parent.setMouseTracking(True)
        parent.installEventFilter(self)

    # __init__()
# catch mouse movements, mouse button presses and keyboard events.    
    def eventFilter(self, _, event):
        if event.type() == Qt.QEvent.MouseMove:
            self.emit(Qt.SIGNAL("MouseMove"), self.parent(), event.pos())
        if event.type() == Qt.QEvent.MouseButtonPress:
            self.emit(Qt.SIGNAL("MouseButtonPress"), self.parent(), event)
        if event.type() == Qt.QEvent.MouseButtonDblClick:
            self.emit(Qt.SIGNAL("MouseButtonDblClick"), self.parent(), event)
        if event.type() == Qt.QEvent.KeyPress:
            self.emit(Qt.SIGNAL("KeyPress"), self.parent(), event)
        return False

    # eventFilter()

# class Spy