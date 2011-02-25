# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
#from flowchart import *
#import os
from advancedTypes import OrderedDict
import pyqtgraph as pg
#import debug
#import FileLoader
#import DatabaseGui
#import FeedbackButton
from metaarray import MetaArray
import numpy as np

class IVCurve(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            ('IV Plot', {'type': 'plot', 'pos': ('right', 'File Loader'), 'size': (800, 300)}),
            ('Data Plot', {'type': 'plot', 'pos': ('bottom',), 'size': (800, 300)}),
        ])
        
        self.initializeElements()

        self.traces = None
        #self.cw = QtGui.QSplitter()
        #self.cw.setOrientation(QtCore.Qt.Vertical)
        #self.setCentralWidget(self.cw)
        #bw = QtGui.QWidget()
        #bwl = QtGui.QHBoxLayout()
        #bw.setLayout(bwl)
        #self.cw.addWidget(bw)
        #self.loadIVBtn = QtGui.QPushButton('Load I/V')
        #bwl.addWidget(self.loadIVBtn)
        #QtCore.QObject.connect(self.loadIVBtn, QtCore.SIGNAL('clicked()'), self.loadIV)
        #self.plot1 = PlotWidget()
        self.plot1 = self.getElement('Data Plot', create=True)
        #self.cw.addWidget(self.plot1)
        #self.plot2 = PlotWidget()
        self.plot2 = self.getElement('IV Plot', create=True)
        #self.cw.addWidget(self.plot2)
        #self.resize(800, 600)
        #self.show()
        self.lr = pg.LinearRegionItem(self.plot1, 'vertical', [0, 1])
        self.plot1.addItem(self.lr)
        self.lr.connect(self.lr, QtCore.SIGNAL('regionChanged'), self.updateAnalysis)


    #def elementChanged(self, element, old, new):
        #name = element.name()
        
        ### connect plots to flowchart, link X axes
        #if name == 'Data Plot':
            #self.flowchart.nodes()['Plot_000'].setPlot(new)
            #p2 = self.getElement('Filter Plot')
            #if p2 is not None:
                #new.setXLink(p2)
        #elif name == 'Filter Plot':
            #self.flowchart.nodes()['Plot_001'].setPlot(new)
            #p2 = self.getElement('Data Plot')
            #if p2 is not None:
                #p2.setXLink(new)

    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        self.plot1.clearPlots()
        dirs = dh.subDirs()
        c = 0.0
        traces = []
        values = []
        for d in dirs:
            d = dh[d]
            try:
                data = d['Clamp1.ma'].read()
            except:
                try:
                    data = d['Clamp2.ma'].read()
                except:
                    continue
            try:
                cmd = data['Channel': 'Command']
            except:
                cmd = data['Channel': 'command']
            if data.hasColumn('Channel', 'primary'):
                data = data['Channel': 'primary']
            else:
                data = data['Channel': 'scaled']
            traces.append(data)
            self.plot1.plot(data, pen=pg.mkPen(hsv=[c, 0.7]))
            values.append(cmd[len(cmd)/2])
            c += 1.0 / len(dirs)
            
        if len(dirs) > 0:
            end = cmd.xvals('Time')[-1]
            self.lr.setRegion([end *0.5, end * 0.6])
            self.updateAnalysis()
            info = [
                {'name': 'Command', 'units': cmd.axisUnits(-1), 'values': np.array(values)},
                data.infoCopy('Time'), 
                data.infoCopy(-1)]
            self.traces = MetaArray(np.vstack(traces), info=info)
            
        return True
        
    def updateAnalysis(self):
        if self.traces is None:
            return
        rgn = self.lr.getRegion()
        data = self.traces['Time': rgn[0]:rgn[1]]
        self.plot2.plot(data.mean(axis=1), clear=True)
        self.plot2.plot(data.max(axis=1))
        self.plot2.plot(data.min(axis=1))
