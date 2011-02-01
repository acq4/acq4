##Needs to:
##    output set of parameters: Ih current, rectification, FI plots (and analysis based on)
##    load IV directory, plot raw data, sends data to a function(flowchart) which returns a list of parameters. 

from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import FileLoader
import DatabaseGui
import FeedbackButton

class IVCurve(AnalysisModule):
    def __init__(self, host, flowchartDir=None):
        AnalysisModule.__init__(self, host)
        
        self.dbIdentity = "IVCurveAnalyzer"  ## how we identify to the database; this determines which tables we own
        
        if flowchartDir is None:
            flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=flowchartDir)
        
        self.flowchart.addInput("dataIn")
        #self.flowchart.addOutput('events')
        self.flowchart.addOutput('regions', multi=True)        
        #self.flowchart.sigChartLoaded.connect(self.connectPlots)
        
        
        ### DBCtrl class is from EventDetector -- need to make my own here
        #self.dbCtrl = DBCtrl(self, identity=self.dbIdentity)
        #self.dbCtrl.storeBtn.clicked.connect(self.storeClicked)
        
        self.ctrl = self.flowchart.widget()
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            #('Database', {'type': 'ctrl', 'object': self.dbCtrl, 'size': (200,300), 'pos': ('bottom', 'File Loader')}),
            ('Data Plot', {'type': 'plot', 'pos': ('right',), 'size': (800, 300)}),
            ('Detection Opts', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'FileLoader'), 'size': (200, 500)}),
            ('IV Plot', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (400, 300)}),
            ('FI Plot', {'type': 'plot', 'pos': ('right', 'IV Plot'), 'size': (400, 300)}),
            ('Output Table', {'type': 'table', 'pos': ('bottom', 'IV Plot'), 'optional': True, 'size': (800,200)}),
        ])
        
        self.initializeElements()
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(flowchartDir, 'default.fc'))
        except:
            debug.printExc('Error loading default flowchart:')
        
        #self.flowchart.sigOutputChanged.connect(self.outputChanged)