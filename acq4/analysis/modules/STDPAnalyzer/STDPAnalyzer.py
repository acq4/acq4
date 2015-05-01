
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
        self.traceSelectRgn.setRegion([0, 300])
        self.plots.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

        self.traces = np.array([], dtype=[('timestamp', float), ('data', object)]) 
        self.averagedTraces = None
        self.lastAverageState = {}
        self.resetAveragedTraces()
        self.files = []


        ### Connect control panel
        self.averageCtrl = pg.WidgetGroup(self.ctrl.traceDisplayGroup) ##TODO: save state when we save data
        self.ctrl.averageTimeSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=60, step=1)
        self.averageCtrl.sigChanged.connect(self.averageCtrlChanged)



    def loadFileRequested(self, files):
        """Called by FileLoader when the load file button is clicked.
                files - a list of the file(s) currently selected in FileLoader
        """
        if files is None:
            return

        n = 0
        for f in files:
            n += len(f.ls())

        with pg.ProgressDialog("Loading data..", 0, n) as dlg:
            for f in files:
                arr = np.zeros((len(f.ls())), dtype=[('timestamp', float), ('data', object)])
                for i, protoDir in enumerate(f.ls()):
                    data = self.dataModel.getClampFile(f[protoDir]).read()
                    timestamp = data.infoCopy()[-1]['startTime']
                    arr[i]['timestamp'] = timestamp
                    arr[i]['data'] = data
                    dlg += 1
                    if dlg.wasCanceled():
                        return
                self.traces = np.concatenate((self.traces, arr))
                self.lastAverageState = {}

        self.updateExptPlot()

    def updateExptPlot(self):
        self.expStart = self.traces['timestamp'].min()
        # self.timeTicks.setXVals(list(self.traces['timestamp']-expStart))
        self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o')
        if self.ctrl.averageCheck.isChecked():
            self.plots.exptPlot.plot(x=self.averagedTraces['avgTimeStamp']-self.expStart, y=y[2]*len(self.averagedTraces), pen=None, symbol='o', symbolBrush=(255,0,0))

    def updateTracesPlot(self):
        rgn = self.traceSelectRgn.getRegion()
        self.plots.tracesPlot.clear()
        if not self.ctrl.averageCheck.isChecked():
            data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)*(self.traces['timestamp'] < rgn[1]+self.expStart)]['data']
            for i, d in enumerate(data):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

        if self.ctrl.averageCheck.isChecked():
            data = self.averagedTraces[(self.averagedTraces['avgTimeStamp'] > rgn[0]+self.expStart)*(self.averagedTraces['avgTimeStamp'] < rgn[1]+self.expStart)]
            displayOrig = self.ctrl.displayTracesCheck.isChecked()
            for i, d in enumerate(data['avgData']):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))
                if displayOrig:
                    for t in data['origTimes']:
                        orig = self.traces[self.traces['timestamp']==t]['data']
                        self.plots.tracesPlot.plot(orig['primary'], pen=pg.intcolor(i, len(data), alpha=100))


    def resetAveragedTraces(self, n=0):
        ## only define the array in one place (here)
        self.averagedTraces = np.zeros(n, dtype=[('avgTimeStamp', float), ('avgData', object), ('origTimes', object)])

    def averageCtrlChanged(self):
        if not self.ctrl.averageCheck.isChecked(): ## if we're not averaging anyway, we don't need to do anything
            return
        if not self.needNewAverage(): ## if the parameters for averaging didn't change, we don't need to do anything
            return

        self.getNewAverages()
        self.updateExptPlot()

    def needNewAverage(self):
        ### Checks if the current values for the averaging controls are the same as when we last averaged
        if self.ctrl.averageTimeRadio.isChecked():
            method = 'time'
            value = self.ctrl.averageTimeSpin.value()
            if (method == self.lastAverageState.get('method', None)) and (value == self.lastAverageState.get('value', None)):
                return False
            else:
                return True

        elif self.ctrl.averageNumberRadio.isChecked():
            method = 'number'
            value = self.ctrl.averageNumberSpin.value()
            if (method == self.lastAverageState.get('method', None)) and (value == self.lastAverageState.get('value', None)):
                return False
            else:
                return True

        else:
            return True


    def getNewAverages(self):

        if self.ctrl.averageTimeRadio.isChecked():
            method = 'time'
            value = self.ctrl.averageTimeSpin.value()
            self.averageByTime(value)
        elif self.ctrl.averageNumberRadio.isChecked():
            method = 'number'
            value = self.ctrl.averageNumberSpin.value()
            self.averageByNumber(value)
        else:
            raise Exception("Unable to average traces. Please make sure an averaging method is selected.")

        self.lastAverageState = {'method': method, 'value': value}

    def averageByTime(self, time):
        t = 0
        i = 0
        n = int((self.traces['timestamp'].max() - self.expStart)/time) + ((self.traces['timestamp'].max() - self.expStart) % time > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)
        while t < len(self.traces):
            traces = self.traces[(self.traces['timestamp'] > self.expStart+time*i)*(self.traces['timestamp'] < self.expStart+time*i+time)]
            if len(traces) > 0:
                x = traces[0]['data']['primary']
                for t2 in traces[1:]:
                    x += t2['data']['primary']
                x /= float(len(traces))
            else:
                continue
            print i, self.averagedTraces.shape
            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            t += len(traces)
            i += 1

    def averageByNumber(self, number):
        t = 0
        i = 0
        n = int(len(traces)/number) + (len(traces) % number > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)

        while t < len(traces):
            traces = self.traces[i:i+number]

            x = traces[0]['data']['primary']
            for t2 in traces[1:]:
                x += t2['data']['primary']
            x /= float(len(traces))

            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            t += len(traces)
            i += 1











    