from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import FileLoader

class EventDetector(AnalysisModule):
    def __init__(self, host):
        path = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=path)
        self.loader = FileLoader.FileLoader(host.dataManager())
        #self.setCentralWidget(self.flowchart.widget())
        #self.ui.chartDock1.setWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        #self.ctrl = QtGui.QLabel('LABEL')
        self.ctrl = self.flowchart.widget()
        self._elements_ = OrderedDict([
            ('fileLoader', {'type': 'fileInput', 'object': self.loader}),
            ('dataPlot', {'type': 'plot', 'pos': ('right', 'fileLoader')}),
            ('ctrl', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'fileLoader')}),
            #('database', {'type': 'database', 'pos': ('below', 'fileInput')}),
            ('filterPlot', {'type': 'plot', 'pos': ('bottom', 'dataPlot')}),
        ])
        
        #print "EventDetector init:", id(EventDetector), id(AnalysisModule)
        #print "  bases:", map(id, EventDetector.__bases__)
        #print "  init fn:", AnalysisModule.__init__, id(AnalysisModule.__init__)
        AnalysisModule.__init__(self, host)
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(path, 'default.fc'))
            
            ## assign plots to their correct spots in the chart
            p1 = self.getElement('dataPlot')
            p2 = self.getElement('filterPlot')
            self.flowchart['Plot_0'].setPlot(p1)
            self.flowchart['Plot_1'].setPlot(p2)
        except:
            debug.printExc('Error loading default flowchart:')
        
        
        
        
        
        