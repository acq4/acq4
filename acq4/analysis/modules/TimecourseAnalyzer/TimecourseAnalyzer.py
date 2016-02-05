from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.DatabaseGui.DatabaseGui import DatabaseGui
from collections import OrderedDict
import numpy as np
import acq4.pyqtgraph as pg

class TimecourseAnalyzer(AnalysisModule):

    """A generic module for analyzing features of repeated traces over time."""

    dbIdentity = "TimecourseAnalyzer"

    def __init__(self, host):
        AnalysisModule.__init__(self, host)

        tables = OrderedDict([
            (self.dbIdentity+'.trials', 'TimecourseAnalyzer_Trials')
        ])
        self.dbGui = DatabaseGui(dm=self.dataManager(), tables=tables)

        self._elements_ = OrderedDict([
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'size':(100,100)}),
            ('AnalysisRegionControl', {'type':'parameterTree', 'pos':('above', 'Database'),'size': (100, 400)}),
            ('File Loader', {'type':'fileInput', 'size': (100, 100), 'pos':('above', 'AnalysisRegionControl'),'host': self}),
            ('Experiment Plot', {'type':'plot', 'pos':('right', 'File Loader'), 'size':(400, 100)}),
            ('Traces Plot', {'type': 'plot', 'pos':('bottom', 'Experiment Plot'), 'size':(400,200)}),
            ('Results', {'type':'table', 'pos':('bottom', 'Traces Plot'), 'size': (400,200)})
        ])
        self.initializeElements()

        self.exptPlot = self.getElement('Experiment Plot', create=True)
        self.tracesPlot = self.getElement('Traces Plot', create=True)
        self.resultsTable = self.getElement('Results', create=True)

        ### initialize variables
        self.expStart = 0
        self.traces = np.array([], dtype=[('timestamp', float), ('data', object)])
        self.files = []


        self.traceSelectRgn = pg.LinearRegionItem()
        self.traceSelectRgn.setRegion([0, 300])
        self.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

    def loadFileRequested(self, files):
        """Called by FileLoader when the load EPSP file button is clicked, once for each selected file.
                files - a list of the file currently selected in FileLoader
        """
        
        if files is None:
            return

        n = len(files[0].ls()) 

        with pg.ProgressDialog("Loading data..", 0, n) as dlg:
            for f in files:
                arr = np.zeros((len(f.ls())), dtype=[('timestamp', float), ('data', object)])
                maxi = -1
                for i, protoDir in enumerate(f.ls()):
                    df = self.dataModel.getClampFile(f[protoDir])
                    if df is None:
                        print 'Error in reading data file %s' % f.name()
                        break
                    data = df.read()
                    timestamp = data.infoCopy()[-1]['startTime']
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
                          *(self.traces['timestamp'] < rgn[1]+self.expStart)]['data']
        
        for i, d in enumerate(data):
            self.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

        
