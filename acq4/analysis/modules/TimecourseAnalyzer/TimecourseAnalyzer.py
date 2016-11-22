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
        
        flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=flowchartDir)
        self.flowchart.addInput('dataIn')
        self.flowchart.addOutput('results')
        self.flowchart.sigChartLoaded.connect(self.connectPlots)

        tables = OrderedDict([(self.dbIdentity+'.traces', 'TimecourseAnalyzer_traces')])
        self.dbGui = DatabaseGui(dm=host.dataManager(), tables=tables)

        self.ctrl = QtGui.QWidget()
        self.ctrl.setLayout(QtGui.QVBoxLayout())
        self.analyzeBtn = QtGui.QPushButton('Analyze')
        self.storeToDBBtn = QtGui.QPushButton('Store to DB')
        self.ctrl.layout().addWidget(self.analyzeBtn)
        self.ctrl.layout().addWidget(self.storeToDBBtn)


        self._elements_ = OrderedDict([
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'size':(100,100)}),
            ('Analysis Options', {'type':'ctrl', 'object': self.flowchart.widget(), 'pos':('above', 'Database'),'size': (100, 400)}),
            ('File Loader', {'type':'fileInput', 'size': (100, 100), 'pos':('above', 'Analysis Options'),'host': self}),
            ('Experiment Plot', {'type':'plot', 'pos':('right', 'File Loader'), 'size':(400, 100)}),
            ('Traces Plot', {'type': 'plot', 'pos':('bottom', 'Experiment Plot'), 'size':(400,200)}),
            ('Results Plot', {'type': 'plot', 'pos':('bottom', 'Traces Plot'), 'size':(400,200)}),
            ('Results Table', {'type':'table', 'pos':('bottom', 'Traces Plot'), 'size': (400,200)}),
            ('Store Ctrl', {'type': 'ctrl', 'object':self.ctrl, 'size':(100,100), 'pos':('bottom', 'File Loader')})
        ])
        self.initializeElements()

        self.exptPlot = self.getElement('Experiment Plot', create=True)
        self.tracesPlot = self.getElement('Traces Plot', create=True)
        self.resultsTable = self.getElement('Results Table', create=True)
        self.resultsTable.setSortingEnabled(False)
        #self.paramTree = self.getElement('Analysis Regions', create=True) 

        ### initialize variables
        self.expStart = 0
        self.traces = np.array([], dtype=[('timestamp', float), ('data', object), ('fileHandle', object), ('results', object)])
        self.files = []


        self.traceSelectRgn = pg.LinearRegionItem()
        self.traceSelectRgn.setRegion([0, 300])
        self.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)
        self.traceSelectRgn.sigRegionChangeFinished.connect(self.updateAnalysis)
        #self.flowchart.sigOutputChanged.connect(self.flowchartOutputChanged)

        #self.addRegionParam = pg.parametertree.Parameter.create(name="Add Region", type='action')
        #self.paramTree.addParameters(self.addRegionParam)
        #self.addRegionParam.sigActivated.connect(self.newRegionRequested)
        self.analyzeBtn.clicked.connect(self.analyzeBtnClicked)
        self.storeToDBBtn.clicked.connect(self.storeToDBBtnClicked)

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
                arr = np.zeros((len(f.ls())), dtype=[('timestamp', float), ('data', object), ('fileHandle', object), ('results', object)])
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

    def updateAnalysis(self):
        self.resultsTable.clear()

        rgn = self.traceSelectRgn.getRegion()
        data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)
                          *(self.traces['timestamp'] < rgn[1]+self.expStart)]
        for i, d in enumerate(data):
            self.flowchart.setInput(dataIn=d['fileHandle'])


    #def flowchartOutputChanged(self):
    #    self.resultsTable.appendData([self.flowchart.output()['results']])

    def analyzeBtnClicked(self, *args):
        for i, t in enumerate(self.traces):
            results = self.flowchart.process(dataIn=t['fileHandle'])
            t['results'] = results['results']

    def storeToDBBtnClicked(self, *args):
        #if len(self.analysisResults) == 0:
        #    self.analyze()

        db = self.dbGui.getDb()
        if db is None:
            raise Exception("No database loaded.")
        
        table = self.dbGui.getTableName(self.dbIdentity+'.traces')

        trialFields = OrderedDict([
            ('CellDir', 'directory:Cell'),
            ('ProtocolSequenceDir', 'directory:ProtocolSequence'),
            ('ProtocolDir', 'directory:Protocol'),
            ('timestamp', 'real'),
            ('time', 'real'),
            ('rmp', 'real'),
            ('pspSlope', 'real'),
            ('maxSlopeTime', 'real'),
            ('pspAmplitude', 'real'),
            ('pspPeakTime', 'real'),
            ('condition', 'text'),
            ('APnumber', 'int'),

            ])

        db.checkTable(table, owner=self.dbIdentity+'.traces', columns=trialFields, create=True, addUnknownColumns=True, indexes=[['ProtocolDir'], ['ProtocolSequenceDir'], ['CellDir']])


        data = np.zeros(len(self.traces), dtype=[
                                                            ('CellDir', object),
                                                            ('ProtocolSequenceDir', object),
                                                            ('ProtocolDir', object),
                                                            ('timestamp', float), 
                                                            ('time', float),
                                                            ('rmp', float), 
                                                            #('inputResistance', float),
                                                            #('tau', float),
                                                            #('bridgeBalance', float)
                                                            ('pspSlope', float),
                                                            #('normalizedPspSlope', float),
                                                            #('slopeFitOffset', float),
                                                            ('maxSlopeTime', float),
                                                            ('pspAmplitude', float),
                                                            ('pspPeakTime', float),
                                                            #('pspRgnStart', float),
                                                            #('pspRgnEnd', float),
                                                            #('analysisCtrlState', object),
                                                            #('averageCtrlState', object),
                                                            #('includedProtocols', object)
                                                            ('condition', str),
                                                            ('APnumber', int)
                                                            ])

        data['CellDir'] = self.dataModel.getParent(self.files[0], 'Cell')
        #data['pspRgnStart'] = self.pspRgn.getRegion()[0]
        #data['pspRgnEnd'] = self.pspRgn.getRegion()[1]
        #data['analysisCtrlState'] = str(self.analysisCtrl.state())
        #data['averageCtrlState'] = str(self.averageCtrl.state())

        #baselineSlope = self.analysisResults[self.analysisResults['time'] < self.expStart+300]['pspSlope'].mean()
        for i in range(len(self.traces)):
            fh = self.traces[i]['fileHandle']
            data[i]['ProtocolDir'] = self.dataModel.getParent(fh, 'Protocol')
            data[i]['ProtocolSequenceDir'] = self.dataModel.getParent(fh, 'ProtocolSequence')
            data[i]['timestamp'] = self.traces[i]['timestamp']
            data[i]['time'] = self.traces[i]['timestamp'] - self.expStart
            data[i]['rmp'] = self.traces[i]['results']['RMP']
            #data[i]['inputResistance'] = self.analysisResults[i]['inputResistance']
            data[i]['pspSlope'] = self.traces[i]['results']['slope']
            #data[i]['normalizedPspSlope'] = self.analysisResults[i]['pspSlope']/baselineSlope
            #data[i]['slopeFitOffset'] = self.analysisResults[i]['slopeFitOffset']
            data[i]['maxSlopeTime'] = self.traces[i]['results']['maxSlopeTime']
            data[i]['pspAmplitude'] = self.traces[i]['results']['amplitude']
            #data[i]['includedProtocols'] = self.averagedTraces[i]['origTimes'] ### TODO: make this protocolDirs instead of timestamps....
            data[i]['pspPeakTime'] = self.traces[i]['results']['pspPeakTime']
            data[i]['condition'] = self.traces[i]['results']['condition']
            data[i]['APnumber'] = self.traces[i]['results']['APnumber']

        old = db.select(table, where={'CellDir':data['CellDir'][0]}, toArray=True)
        if old is not None: ## only do deleting if there is already data stored for this cell
            db.delete(table, where={'CellDir': data['CellDir'][0]})
        
        db.insert(table, data)


    


        
