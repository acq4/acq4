# -*- coding: utf-8 -*-
__author__ = 'pbmanis'

"""
TraceAnalysis provides a platform for the analysis of voltage or current traces.
The module provides standard tools to access data and databases, and flowcharts.
Two "trace" windows (PSP Plot and Data Plot) are provided to facilitate interactive
adjustment of analysis parameters.
Three "scatter plots" are provided on the right for summary analysis.
The output data is placed into a table.
The specifics of the analysis depends on the choice of the flowchart.
12/5/2013 pbmanis
"""

from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
import lib.analysis.modules.EventDetector as EventDetector
from collections import OrderedDict
import pyqtgraph as pg
from metaarray import MetaArray
#from DBCtrl import DBCtrl
import numpy as np
from DirTreeWidget import DirTreeLoader
from FileLoader import FileLoader
import pyqtgraph.flowchart as fc
import pyqtgraph.debug as debug
import os
import lib.analysis.scripts.chr2analysis as ChR2

class TraceAnalyzer(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        fcpath = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        confpath = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "configs")
        self.dbIdentity = "TraceAnalysis"  ## how we identify to the database; this determines which tables we own

        self.confWidget = QtGui.QWidget()
        self.confLoader = ConfLoader(self, confpath)
        self.fileLoader = DataLoader(self, host.dataManager())
        self.addPlotBtn = QtGui.QPushButton('Add Plot')
        self.processWidget = QtGui.QWidget()
        self.processLayout = QtGui.QHBoxLayout()
        self.processWidget.setLayout(self.processLayout)
        self.processBtn = QtGui.QPushButton('Process')
        self.processCheck = QtGui.QCheckBox('Auto')
        self.processLayout.addWidget(self.processBtn)
        self.processLayout.addWidget(self.processCheck)
        self.confLayout = QtGui.QGridLayout()
        self.confWidget.setLayout(self.confLayout)
        self.confLayout.addWidget(self.confLoader, 0, 0)
        self.confLayout.addWidget(self.addPlotBtn, 1, 0)
        self.confLayout.addWidget(self.processWidget, 2, 0)
        
        self.plots = []
        
        self.params = None
        self.data = None

        ## setup map DB ctrl
        #self.dbCtrl = DBCtrl(self, self.dbIdentity)

        self.flowchart = fc.Flowchart(filePath=fcpath)
        self.flowchart.addInput('Input')
        self.flowchart.addOutput('Output')
        #self.flowchart.sigChartLoaded.connect(self.connectPlots)
        ## create event detector
        fcDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "detector_fc")
       # self.detector = EventDetector.EventDetector(host, flowchartDir=fcDir, dbIdentity=self.dbIdentity+'.events')

        self.flowchart.sigChartLoaded.connect(self.connectPlots)

        #elems = self.detector.listElements()
        #print elems

        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('Configuration', {'type': 'ctrl', 'object': self.confWidget, 'size': (200,200)}),
            ('File Loader', {'type': 'ctrl', 'object': self.fileLoader, 'size': (200, 300), 'pos': ('above', 'Configuration')}),
            ('Flowchart', {'type': 'ctrl', 'object': self.flowchart.widget(), 'size': (400,500), 'pos': ('right', 'Configuration')}),
            ('Data Plot', {'type': 'plot', 'pos': ('bottom', 'Flowchart'), 'size': (400,300)}),
            ('PSP Plot', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (400,300)}),
            ('Scatter Plot1', {'type': 'plot',  'pos': ('right',), 'size': (300,300)}),
            ('Scatter Plot2', {'type': 'plot',  'pos': ('bottom', 'Scatter Plot1'), 'size': (300,300)}),
            ('Scatter Plot3', {'type': 'plot',  'pos': ('bottom', 'Scatter Plot2'), 'size': (300,300)}),
            ('Results', {'type': 'table', 'size': (500,200), 'pos': 'bottom'}),
        ])
        self.initializeElements()
        
        self.addPlotBtn.clicked.connect(self.addPlotClicked)
        self.processBtn.clicked.connect(self.processClicked)
        self.flowchart.sigOutputChanged.connect(self.outputChanged)
        self.fileLoader.sigFileLoaded.connect(self.fileLoaded)
        self.fileLoader.sigSelectedFileChanged.connect(self.fileSelected)

    def fileLoaded(self, dh):
        files = self.fileLoader.loadedFiles()
        self.flowchart.setInput(Input=files[0])
        table = self.getElement('Results')
        table.setData(None)
        ChR2.clearSummary()
        
    def fileSelected(self, dh):
        self.flowchart.setInput(Input=dh)

    def connectPlots(self):
        plots = ['Data Plot', 'PSP Plot']
        for plotName in plots:
            dp = self.getElement(plotName, create=False)
            if dp is not None and plotName in self.flowchart.nodes().keys():
                self.flowchart.nodes()[plotName].setPlot(dp)

    def addPlotClicked(self):
        plot = pg.PlotWidget()
        self.plots.append(plot)
        
        node = self.flowchart.createNode('PlotWidget')
        name = node.name()
        node.setPlot(plot)
        
        dock = self._host_.dockArea.addDock(name=name, position='bottom')
        dock.addWidget(plot)
        #dock.setTitle(name)
        
    def processClicked(self):
       # print ChR2.getSummary()
        ChR2.clearSummary()

        output = []
        table = self.getElement('Results')
        for fh in self.fileLoader.loadedFiles():
            try:
                res = self.flowchart.process(Input=fh)
                output.append(res) # [res[k] for k in res.keys()])
            except:
                debug.printExc('Error processing %s' % fh)
        table.setData(output)
        pl = []
        for i in ['1', '2', '3']:
            name = 'Scatter Plot%s' % i
            pl.append(self.getElement(name, create=False))
            ChR2.printSummary(plotWidget = pl)

    def outputChanged(self):
        if self.processCheck.isChecked():
            self.processClicked()


class ConfLoader(DirTreeLoader):
    def __init__(self, host, path):
        self.host = host
        DirTreeLoader.__init__(self, path)
        
    def new(self):
        print("new")
        return True
        
    def load(self, handle):
        print('load %s' % str(handle))
        
    def save(self, handle):
        print('save %s' % str(handle))
        
class DataLoader(FileLoader):
    def __init__(self, host, dm):
        self.host = host
        FileLoader.__init__(self, dm)
        
    def loadFile(self, files):
        if len(files) != 1:
            raise Exception('Must select exactly 1 protocol directory to load')
        
        self.loaded = []
        self.ui.fileTree.clear()
        
        dh = files[0]
        for fileName in dh.ls():
            handle = dh[fileName]
            self.loaded.append(handle)
            #name = fh.name(relativeTo=self.ui.dirTree.baseDirHandle())
            item = QtGui.QTreeWidgetItem([fileName])
            item.file = handle
            self.ui.fileTree.addTopLevelItem(item)
        self.sigFileLoaded.emit(dh)
            
    def selectedFileChanged(self):
        sel = self.ui.fileTree.currentItem()
        if sel is not None:
            self.sigSelectedFileChanged.emit(sel.file)
         