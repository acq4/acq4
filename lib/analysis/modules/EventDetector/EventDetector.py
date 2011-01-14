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
            ('fileLoader', {'type': 'fileInput', 'object': self.loader, 'size': (200, 300)}),
            ('dataPlot', {'type': 'plot', 'pos': ('right', 'fileLoader'), 'size': (800, 400)}),
            ('ctrl', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'fileLoader'), 'size': (200, 500)}),
            #('database', {'type': 'database', 'pos': ('below', 'fileInput')}),
            ('filterPlot', {'type': 'plot', 'pos': ('bottom', 'dataPlot'), 'size': (800, 400)}),
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
            self.flowchart.nodes()['Plot_000'].setPlot(p1)
            self.flowchart.nodes()['Plot_001'].setPlot(p2)
            
            ## link plot X axes
            p1.setXLink(p2)
        except:
            debug.printExc('Error loading default flowchart:')
        
        QtCore.QObject.connect(self.loader, QtCore.SIGNAL('fileLoaded'), self.fileLoaded)
        
    def fileLoaded(self, fh):
        print 'loaded'
        self.flowchart.setInput(dataIn=fh)
        
        
        
        