# -*- coding: utf-8 -*-
from __future__ import print_function
"""
"""

from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import pyqtgraph as pg
from pyqtgraph.metaarray import MetaArray
import numpy as np
from acq4.util.DirTreeWidget import DirTreeLoader
from acq4.util.FileLoader import FileLoader
import pyqtgraph.flowchart as fc
import pyqtgraph.debug as debug
import os

class TraceAnalyzer(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        fcpath = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        confpath = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "configs")
        
        self.confWidget = Qt.QWidget()
        self.confLoader = ConfLoader(self, confpath)
        self.fileLoader = DataLoader(self, host.dataManager())
        self.addPlotBtn = Qt.QPushButton('Add Plot')
        self.processWidget = Qt.QWidget()
        self.processLayout = Qt.QHBoxLayout()
        self.processWidget.setLayout(self.processLayout)
        self.processBtn = Qt.QPushButton('Process')
        self.processCheck = Qt.QCheckBox('Auto')
        self.processLayout.addWidget(self.processBtn)
        self.processLayout.addWidget(self.processCheck)
        self.confLayout = Qt.QGridLayout()
        self.confWidget.setLayout(self.confLayout)
        self.confLayout.addWidget(self.confLoader, 0, 0)
        self.confLayout.addWidget(self.addPlotBtn, 1, 0)
        self.confLayout.addWidget(self.processWidget, 2, 0)
        
        self.plots = []
        
        self.params = None
        self.data = None
        
        self.flowchart = fc.Flowchart(filePath=fcpath)
        self.flowchart.addInput('Input')
        self.flowchart.addOutput('Output')
        #self.flowchart.sigChartLoaded.connect(self.connectPlots)
        
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('Configuration', {'type': 'ctrl', 'object': self.confWidget, 'size': (200,200)}),
            ('File Loader', {'type': 'ctrl', 'object': self.fileLoader, 'size': (200, 300), 'pos': ('bottom', 'Configuration')}),
            ('Flowchart', {'type': 'ctrl', 'object': self.flowchart.widget(), 'size': (300,500), 'pos': ('right',)}),
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
        
    def fileSelected(self, dh):
        self.flowchart.setInput(Input=dh)
        
        
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
        output = []
        
        table = self.getElement('Results')
        for fh in self.fileLoader.loadedFiles():
            try:
                output.append(self.flowchart.process(Input=fh))
            except:
                debug.printExc('Error processing %s' % fh)
        table.setData(output)
    
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
            item = Qt.QTreeWidgetItem([fileName])
            item.file = handle
            self.ui.fileTree.addTopLevelItem(item)
        self.sigFileLoaded.emit(dh)
            
    def selectedFileChanged(self):
        sel = self.ui.fileTree.currentItem()
        if sel is not None:
            self.sigSelectedFileChanged.emit(sel.file)
         