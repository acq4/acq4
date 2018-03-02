##Needs to:
##    output set of parameters: Ih current, rectification, FI plots (and analysis based on)
##    load IV directory, plot raw data, sends data to a function(flowchart) which returns a list of parameters. 
from __future__ import print_function

from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.pyqtgraph.functions import mkPen
from acq4.util.flowchart import *
import os
from collections import OrderedDict
import acq4.util.debug as debug
import acq4.util.FileLoader as FileLoader
import acq4.util.DatabaseGui as DatabaseGui
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
            ('Detection Opts', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'File Loader'), 'size': (200, 500)}),
            ('IV Plot', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (400, 300)}),
            ('Output Table', {'type': 'table', 'pos': ('bottom', 'IV Plot'), 'optional': True, 'size': (800,200)}),
            ('FI Plot', {'type': 'plot', 'pos': ('right', 'IV Plot'), 'size': (400, 300)}),
        ])
        
        self.initializeElements()
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(flowchartDir, 'default.fc'))
        except:
            debug.printExc('Error loading default flowchart:')
        
        #self.flowchart.sigOutputChanged.connect(self.outputChanged)
        
    def loadFileRequested(self, fh):
        """Called by file loader when a file load is requested."""
        ### This should load a whole directory of cciv, plot them, put traces into one array and send that array to the flowchart.
        if fh.isDir():
            dirs = [d for d in fh.subDirs()]
        else:
            dirs = [fh]
            
        dataPlot = self.getElement('Data Plot')
        
        ## Attempt to stick all the traces into one big away -- not sure I like this because you lose the metaInfo.
        a = fh[dirs[0]]['Clamp1.ma'].read()
        data = np.empty((a.shape[0], a.shape[1], len(dirs)), dtype=np.float)        
        
        n=0
        for d in dirs:
            trace = fh[d]['Clamp1.ma'].read()
            data[:,:,n] = trace
            color = float(n)/(len(dirs))*0.7
            pen = mkPen(hsv=[color, 0.8, 0.7])
            dataPlot.plot(trace['Channel':'primary'], pen=pen)
            n += 1 
    
        self.flowchart.setInput(dataIn=data)
        self.currentFile = fh
        return True