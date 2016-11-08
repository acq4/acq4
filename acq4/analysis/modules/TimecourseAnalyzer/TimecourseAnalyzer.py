from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.DatabaseGui.DatabaseGui import DatabaseGui
from acq4.util.flowchart import *
from collections import OrderedDict
import numpy as np
import acq4.pyqtgraph as pg
from RegionParameter import RegionParameter
import os
#from acq4.pyqtgraph.parametertree import Parameter

class TimecourseAnalyzer(AnalysisModule):

    """A generic module for analyzing features of repeated traces over time."""

    dbIdentity = "TimecourseAnalyzer"

    def __init__(self, host):
        AnalysisModule.__init__(self, host)

        tables = OrderedDict([
            (self.dbIdentity+'.trials', 'TimecourseAnalyzer_Trials')
        ])
        self.dbGui = DatabaseGui(dm=self.dataManager(), tables=tables)

        
        flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=flowchartDir)
        self.flowchart.addInput('dataIn')
        self.flowchart.addOutput('results')
        self.flowchart.sigChartLoaded.connect(self.connectPlots)

        self._elements_ = OrderedDict([
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'size':(100,100)}),
            ('Analysis Options', {'type':'ctrl', 'object': self.flowchart.widget(), 'pos':('above', 'Database'),'size': (100, 400)}),
            ('File Loader', {'type':'fileInput', 'size': (100, 100), 'pos':('above', 'Analysis Options'),'host': self}),
            ('Experiment Plot', {'type':'plot', 'pos':('right', 'File Loader'), 'size':(400, 100)}),
            ('Traces Plot', {'type': 'plot', 'pos':('bottom', 'Experiment Plot'), 'size':(400,200)}),
            ('Results Plot', {'type': 'plot', 'pos':('bottom', 'Traces Plot'), 'size':(400,200)}),
            ('Results Table', {'type':'table', 'pos':('bottom', 'Traces Plot'), 'size': (400,200)})
        ])
        self.initializeElements()

        self.exptPlot = self.getElement('Experiment Plot', create=True)
        self.tracesPlot = self.getElement('Traces Plot', create=True)
        self.resultsTable = self.getElement('Results Table', create=True)
        #self.paramTree = self.getElement('Analysis Regions', create=True) 

        ### initialize variables
        self.expStart = 0
        self.traces = np.array([], dtype=[('timestamp', float), ('data', object), ('fileHandle', object)])
        self.files = []


        self.traceSelectRgn = pg.LinearRegionItem()
        self.traceSelectRgn.setRegion([0, 300])
        self.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

        #self.addRegionParam = pg.parametertree.Parameter.create(name="Add Region", type='action')
        #self.paramTree.addParameters(self.addRegionParam)
        #self.addRegionParam.sigActivated.connect(self.newRegionRequested)

    def connectPlots(self):
        dp = self.getElement('Traces Plot', create=False)
        #fp = self.getElement('Filter Plot', create=False)
        if dp is not None and 'Plot_000' in self.flowchart.nodes().keys():
            self.flowchart.nodes()['Plot_000'].setPlot(dp)
        #if fp is not None and 'Plot_001' in self.flowchart.nodes().keys():
        #    self.flowchart.nodes()['Plot_001'].setPlot(fp)

    def loadFileRequested(self, files):
        """Called by FileLoader when the load EPSP file button is clicked, once for each selected file.
                files - a list of the file currently selected in FileLoader
        """
        
        if files is None:
            return

        n = len(files[0].ls()) 

        with pg.ProgressDialog("Loading data..", 0, n) as dlg:
            for f in files:
                arr = np.zeros((len(f.ls())), dtype=[('timestamp', float), ('data', object), ('fileHandle', object)])
                maxi = -1
                for i, protoDir in enumerate(f.ls()):
                    df = self.dataModel.getClampFile(f[protoDir])
                    if df is None:
                        print 'Error in reading data file %s' % f.name()
                        break
                    data = df.read()
                    timestamp = data.infoCopy()[-1]['startTime']
                    arr[i]['fileHandle'] = df
                    arr[i]['timestamp'] = timestamp
                    arr[i]['data'] = data
                    maxi += 1  # keep track of successfully read traces
                    dlg += 1
                    if dlg.wasCanceled():
                        return
                self.traces = np.concatenate((self.traces, arr[:maxi]))  # only concatenate successfully read traces
                #self.lastAverageState = {}
                self.files.append(f)
        
        self.expStart = self.traces['timestamp'].min()
        #self.averageCtrlChanged()
        self.updateExptPlot()
        self.updateTracesPlot()
        return True

    def updateExptPlot(self):
        """Update the experiment plots with markers for the the timestamps of 
        all loaded EPSP traces, and averages (if selected in the UI)."""

        if len(self.traces) == 0:
            return

        self.exptPlot.clear()
        self.exptPlot.addItem(self.traceSelectRgn)

        self.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o', symbolSize=6)

    def updateTracesPlot(self):
        """Update the Trace display plot to show the traces corresponding to
         the timestamps selected by the region in the experiment plot."""

        rgn = self.traceSelectRgn.getRegion()
        self.tracesPlot.clear()

        ### plot all the traces with timestamps within the selected region (according to self.traceSelectRgn)
        data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)
                          *(self.traces['timestamp'] < rgn[1]+self.expStart)]
        
        for i, d in enumerate(data['data']):
            self.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

        self.flowchart.setInput(dataIn=data[0]['fileHandle'])

    #def newRegionRequested(self):
    #    self.paramTree.addParameters(RegionParameter(self.tracesPlot))

        
