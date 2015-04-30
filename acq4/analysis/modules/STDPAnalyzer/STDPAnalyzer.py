
from PyQt4 import QtGui, QtCore
from collections import OrderedDict
from acq4.analysis.AnalysisModule import AnalysisModule
import STDPControlTemplate, STDPPlotsTemplate
import acq4.pyqtgraph as pg
import numpy as np


class STDPAnalyzer(AnalysisModule):

    dbIdentity = "STDPAnalyzer"

    def __init__(self, host):
        AnalysisModule.__init__(self, host)

        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = STDPControlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)

       
        self.plotsWidget = QtGui.QWidget()
        self.plots = STDPPlotsTemplate.Ui_Form()
        self.plots.setupUi(self.plotsWidget)

        # ### Plots accessible through self.plots - defined above:
        #     exptPlot - displays the time when traces were recorded. Used to choose which traces are displayed in tracesPlot
        #     tracesPlot - displays data traces
        #     plasticityPlot - displays a measure of synaptic plasticity over the course of the experimetn
        #     RMP_plot - displays the resting membrane potential (or holding current) over the course of the Experiment
        #     RI_plot - displays the input resistance over the course of the experiment

        self._elements_ = OrderedDict([
            ('File Loader', {'type':'fileInput', 'host':self, 'showFileTree':True, 'size': (160, 100)}),
            ('Control Panel', {'type':'ctrl', 'object': self.ctrlWidget, 'pos':('below', 'File Loader'),'size': (160, 400)}),
            ('Plots', {'type': 'ctrl', 'object': self.plotsWidget, 'pos': ('right', 'File Loader'), 'size': (400, 700)})
        ])
        self.initializeElements()
           
        
        ## Set labels/titles on plots
        self.plots.exptPlot.setTitle('Experiment Timecourse')
        self.plots.tracesPlot.setLabel('left', "Voltage") ### TODO: check whether traces are in VC or IC
        self.plots.tracesPlot.setTitle("Data")
        self.plots.plasticityPlot.setLabel('left', 'Slope')
        self.plots.plasticityPlot.setTitle('Plasticity')
        self.plots.RMP_plot.setTitle('Resting Membrane Potential')
        self.plots.RMP_plot.setLabel('left', 'Voltage')
        self.plots.RI_plot.setLabel('left', 'Resistance')
        self.plots.RI_plot.setTitle('Input Resistance')

        for p in [self.plots.exptPlot, self.plots.tracesPlot, self.plots.plasticityPlot, self.plots.RMP_plot, self.plots.RI_plot]:
            p.setLabel('bottom', 'Time')

        self.traceSelectRgn = pg.LinearRegionItem()
        self.plots.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

        self.traces = np.array([], dtype=[('timestamp', float), ('data', object)]) 
        self.files = []
        #self.timeTicks = pg.VTickGroup(yrange=[0,1])

        #self.plots.exptPlot.addItem(self.timeTicks)


    def loadFileRequested(self, files):
        """Called by FileLoader when the load file button is clicked.
                files - a list of the file(s) currently selected in FileLoader
        """
        if files is None:
            return

        for f in files:
            arr = np.zeros((len(f.ls())), dtype=[('timestamp', float), ('data', object)])
            for i, protoDir in enumerate(f.ls()):
                data = self.dataModel.getClampFile(f[protoDir]).read()
                timestamp = data.infoCopy()[-1]['startTime']
                arr[i]['timestamp'] = timestamp
                arr[i]['data'] = data
            self.traces = np.concatenate((self.traces, arr))

        self.updateExptPlot()

    def updateExptPlot(self):
        self.expStart = self.traces['timestamp'].min()
        # self.timeTicks.setXVals(list(self.traces['timestamp']-expStart))
        self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o')

    def updateTracesPlot(self):
        print "updateTracesPlot"
        rgn = self.traceSelectRgn.getRegion()
        print rgn
        data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)*(self.traces['timestamp'] < rgn[1]+self.expStart)]['data']
        print data.shape
        self.plots.tracesPlot.clear()
        for d in data:
            self.plots.tracesPlot.plot(d['primary'])







    