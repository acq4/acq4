
from PyQt4 import QtGui, QtCore
from collections import OrderedDict
from acq4.analysis.AnalysisModule import AnalysisModule
import STDPControlTemplate, STDPPlotsTemplate
import acq4.pyqtgraph as pg
import numpy as np
from acq4.util.functions import measureResistance
from acq4.util.DatabaseGui.DatabaseGui import DatabaseGui


class STDPAnalyzer(AnalysisModule):

    dbIdentity = "STDPAnalyzer"

    def __init__(self, host):
        AnalysisModule.__init__(self, host)

        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = STDPControlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)

        tables = OrderedDict([
            (self.dbIdentity+'.trials', 'STDP_Trials'),
            (self.dbIdentity+'.cell', 'STDP_Cell')
        ])
        self.dbGui = DatabaseGui(dm=self.dataManager(), tables=tables)

       
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
            ('File Loader', {'type':'fileInput', 'host':self, 'showFileTree':True, 'size': (100, 100)}),
            ('Control Panel', {'type':'ctrl', 'object': self.ctrlWidget, 'pos':('below', 'File Loader'),'size': (100, 400)}),
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'pos':('bottom', 'Control Panel'), 'size':(100,100)}),
            ('Plots', {'type': 'ctrl', 'object': self.plotsWidget, 'pos': ('right', 'File Loader'), 'size': (400, 700)})
        ])
        self.initializeElements()
           
        
        ## Set labels/titles on plots  -- takes a lot of space
        # self.plots.exptPlot.setTitle('Experiment Timecourse')
        # self.plots.tracesPlot.setLabel('left', "Voltage") ### TODO: check whether traces are in VC or IC
        # self.plots.tracesPlot.setTitle("Data")
        self.plots.plasticityPlot.setLabel('left', 'Slope')
        # self.plots.plasticityPlot.setTitle('Plasticity')
        # self.plots.RMP_plot.setTitle('Resting Membrane Potential')
        self.plots.RMP_plot.setLabel('left', 'Voltage')
        self.plots.RI_plot.setLabel('left', 'Resistance')
        # self.plots.RI_plot.setTitle('Input Resistance')

        for p in [self.plots.exptPlot, self.plots.tracesPlot, self.plots.plasticityPlot, self.plots.RMP_plot, self.plots.RI_plot]:
            p.setLabel('bottom', 'Time')

        ## Set up measurement regions in plots
        self.traceSelectRgn = pg.LinearRegionItem()
        self.traceSelectRgn.setRegion([0, 300])
        self.plots.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

        self.baselineRgn = pg.LinearRegionItem(brush=(0,150,0,50))
        self.plots.tracesPlot.addItem(self.baselineRgn)
        
        self.pspRgn = pg.LinearRegionItem(brush=(150,0,0,50))
        self.plots.tracesPlot.addItem(self.pspRgn)

        self.healthRgn = pg.LinearRegionItem(brush=(0,0,150,50))
        self.plots.tracesPlot.addItem(self.healthRgn)

        ### Connect control panel
        self.averageCtrl = pg.WidgetGroup(self.ctrl.traceDisplayGroup) ##TODO: save state when we save data
        self.ctrl.averageTimeSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=60, step=1)
        self.ctrl.averageNumberSpin.setOpts(step=1, dec=True)
        self.averageCtrl.sigChanged.connect(self.averageCtrlChanged)

        self.analysisCtrl = pg.WidgetGroup(self.ctrl.analysisGroup)
        self.ctrl.baselineCheck.toggled.connect(self.regionDisplayToggled)
        self.ctrl.pspCheck.toggled.connect(self.regionDisplayToggled)
        self.ctrl.healthCheck.toggled.connect(self.regionDisplayToggled)

        self.ctrl.baselineStartSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.baselineEndSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.baselineStartSpin.valueChanged.connect(self.baselineSpinChanged)
        self.ctrl.baselineEndSpin.valueChanged.connect(self.baselineSpinChanged)
        self.baselineRgn.sigRegionChangeFinished.connect(self.baselineRgnChanged)

        self.ctrl.pspStartSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.pspEndSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.pspStartSpin.valueChanged.connect(self.pspSpinChanged)
        self.ctrl.pspEndSpin.valueChanged.connect(self.pspSpinChanged)
        self.pspRgn.sigRegionChangeFinished.connect(self.pspRgnChanged)

        self.ctrl.healthStartSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.healthEndSpin.setOpts(suffix='s', siPrefix=True, dec=True, step=1, minStep=0.001)
        self.ctrl.healthStartSpin.valueChanged.connect(self.healthSpinChanged)
        self.ctrl.healthEndSpin.valueChanged.connect(self.healthSpinChanged)
        self.healthRgn.sigRegionChangeFinished.connect(self.healthRgnChanged)

        self.ctrl.analyzeBtn.clicked.connect(self.analyze)

        self.baselineRgn.setRegion((0,0.05))
        self.pspRgn.setRegion((0.052,0.067))
        self.healthRgn.setRegion((0.24,0.34))

        self.ctrl.measureAvgSpin.setOpts(step=1, dec=True)
        self.ctrl.measureModeCombo.addItems(['Slope (max)', 'Amplitude (max)'])

        ### Set up internal information storage
        self.traces = np.array([], dtype=[('timestamp', float), ('data', object)]) 
        self.excludedTraces = np.array([], dtype=[('timestamp', float), ('data', object)])
        self.averagedTraces = None
        self.resetAveragedTraces()
        self.lastAverageState = {}
        self.files = []






    def loadFileRequested(self, files):
        """Called by FileLoader when the load file button is clicked, once for each selected file.
                files - a list of the file currently selected in FileLoader
        """
        #print "loadFileRequested"
        if files is None:
            return

        # n = 0
        # for f in files:
        #     n += len(f.ls())
        # print "   ", n
        n = len(files[0].ls()) 

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
        #print "   ", len(self.traces)
        self.updateExptPlot()
        self.updateTracesPlot()
        return True

    def updateExptPlot(self):
        if len(self.traces) == 0:
            return

        self.expStart = self.traces['timestamp'].min()
        self.plots.exptPlot.clear()
        self.plots.exptPlot.addItem(self.traceSelectRgn)

        if self.ctrl.averageCheck.isChecked():
            #print "updateExptPlot", len(self.traces), len(self.averagedTraces)
            self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o', alpha=50)
            self.plots.exptPlot.plot(x=self.averagedTraces['avgTimeStamp']-self.expStart, y=[2]*len(self.averagedTraces), pen=None, symbol='o', symbolBrush=(255,0,0))
        else:
            self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o')

        if self.ctrl.excludeAPsCheck.isChecked():
            self.plots.exptPlot.plot(x=self.excludedTraces['timestamp']-self.expStart, y=[1]*len(self.excludedTraces), pen=None, symbol='o', symbolBrush=(255,100,100))

    def clearTracesPlot(self):
        self.plots.tracesPlot.clear()
        for item in [self.baselineRgn, self.pspRgn, self.healthRgn]:
            self.plots.tracesPlot.addItem(item)

    def updateTracesPlot(self):
        rgn = self.traceSelectRgn.getRegion()
        self.clearTracesPlot()

        if not self.ctrl.averageCheck.isChecked():
            data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)*(self.traces['timestamp'] < rgn[1]+self.expStart)]['data']
            for i, d in enumerate(data):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

        if self.ctrl.averageCheck.isChecked():
            data = self.averagedTraces[(self.averagedTraces['avgTimeStamp'] > rgn[0]+self.expStart)*(self.averagedTraces['avgTimeStamp'] < rgn[1]+self.expStart)]
            displayOrig = self.ctrl.displayTracesCheck.isChecked()
            #print "   len(data):", len(data)
            for i, d in enumerate(data['avgData']):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))
                if displayOrig:
                    #print "   origTimes:", data['origTimes'] , type(data['origTimes']), type(data['origTimes'][0])
                    for t in data['origTimes'][i]:
                        orig = self.traces[self.traces['timestamp']==t]['data'][0]
                        #sample = self.traces[0]['data']
                        #print orig.infoCopy()
                        #print sample.infoCopy()
                        self.plots.tracesPlot.plot(orig['primary'], pen=pg.intColor(i, len(data), alpha=30))


    def resetAveragedTraces(self, n=0):
        ## only define the array in one place (here)
        self.averagedTraces = np.zeros(n, dtype=[('avgTimeStamp', float), ('avgData', object), ('origTimes', object)])

    def averageCtrlChanged(self):
        if not self.ctrl.averageCheck.isChecked(): ## if we're not averaging anyway, we don't need to do anything
            self.updateExptPlot()
            self.updateTracesPlot()
            return
        if not self.needNewAverage(): ## if the parameters for averaging didn't change, we don't need to do anything
            self.updateTracesPlot()
            return

        self.getNewAverages()
        self.updateExptPlot()
        self.updateTracesPlot()

    def needNewAverage(self):
        ### Checks if the current values for the averaging controls are the same as when we last averaged
        excludeAPs = self.ctrl.excludeAPsCheck.isChecked()
        if not excludeAPs == self.lastAverageState.get('excludeAPs', None):
            return True

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

        excludeAPs = self.ctrl.excludeAPsCheck.isChecked()

        if self.ctrl.averageTimeRadio.isChecked():
            method = 'time'
            value = self.ctrl.averageTimeSpin.value()
            self.averageByTime(value, excludeAPs=excludeAPs)
        elif self.ctrl.averageNumberRadio.isChecked():
            method = 'number'
            value = self.ctrl.averageNumberSpin.value()
            self.averageByNumber(value, excludeAPs=excludeAPs)
        else:
            raise Exception("Unable to average traces. Please make sure an averaging method is selected.")

        self.lastAverageState = {'method': method, 'value': value, 'excludeAPs':excludeAPs}
        #print "finished getNewAverages"

    def checkForAP(self, trace, timeWindow):
        """Return True if there is an action potential present in the trace in the given timeWindow (tuple of start, stop)."""
        print 'checkforAP called.'
        data = trace['primary']['Time':timeWindow[0]:timeWindow[1]]
        if data.max() > -0.02:
            return True
        else:
            return False

    def averageByTime(self, time, excludeAPs=False):
        # print "averageByTime called."
        
        # k = 0 ## how many excluded traces we have
        n = int((self.traces['timestamp'].max() - self.expStart)/time) + ((self.traces['timestamp'].max() - self.expStart) % time > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)
        #print "   computed numbers, reset average array. "
        # print "      n:", n
        # print "      timestamp.max():", self.traces['timestamp'].max()
        # print "      expStart:", self.expStart
        # print "      timestamp.min():", self.traces['timestamp'].min()
        # print "      time:", time
        if excludeAPs:
            #print '   excluding APs:'
            APmask = np.zeros(len(self.traces), dtype=bool)
            for i, trace in enumerate(self.traces):
                APmask[i] = self.checkForAP(trace['data'], (0, 0.25))
            self.excludedTraces = self.traces[APmask]
            includedTraces = self.traces[~APmask]
        else:
            includedTraces = self.traces

        #print "   averaging traces:"
        t = 0 ## how many traces we've gone through
        i = 0 ## how many timesteps we've gone through
        while t < len(includedTraces):
            #raise Exception("Stop!")
            traces = includedTraces[(includedTraces['timestamp'] >= self.expStart+time*i)*(includedTraces['timestamp'] < self.expStart+time*i+time)]
            if len(traces) > 1:
                x = traces[0]['data']
                for trace2 in traces[1:]:
                    x += trace2['data']
                x /= len(traces)
            elif len(traces) == 1:
                x = traces[0]['data']
            else:
                i += 1
                #print t, len(includedTraces), len(traces)
                continue
            #print "   averaged set ", i
            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            #print "   assigned values for set", i
            t += len(traces)
            i += 1
            #print t, len(includedTraces)

            #print (len(self.averagedTraces[self.averagedTraces['avgTimeStamp'] <= self.expStart]))
        self.averagedTraces = self.averagedTraces[self.averagedTraces['avgTimeStamp'] != 0] ## clean up any left over zeros from pauses in data collection
        #self.excludedTraces = self.excludedTraces[self.excludedTraces['timestamp'] != 0]
        #print "  finished averaging"


    def averageByNumber(self, number, excludeAPs=False):
        n = int(len(self.traces)/number) + (len(self.traces) % number > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)

        if excludeAPs:
            #print '   excluding APs:'
            APmask = np.zeros(len(self.traces), dtype=bool)
            for i, trace in enumerate(self.traces):
                APmask[i] = self.checkForAP(trace['data'], (0, 0.25))
            self.excludedTraces = self.traces[APmask]
            includedTraces = self.traces[~APmask]
        else:
            includedTraces = self.traces

        t = 0
        i = 0
        while t < len(includedTraces):
            traces = includedTraces[i*number:i*number+number]

            x = traces[0]['data']['primary']
            for t2 in traces[1:]:
                x += t2['data']['primary']
            x /= float(len(traces))

            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            t += len(traces)
            i += 1

    def regionDisplayToggled(self):
        if self.ctrl.baselineCheck.isChecked():
            self.baselineRgn.show()
        else:
            self.baselineRgn.hide()

        if self.ctrl.pspCheck.isChecked():
            self.pspRgn.show()
        else:
            self.pspRgn.hide()

        if self.ctrl.healthCheck.isChecked():
            self.healthRgn.show()
        else:
            self.healthRgn.hide()

    def baselineRgnChanged(self):
        try:
            self.ctrl.baselineStartSpin.blockSignals(True)
            self.ctrl.baselineEndSpin.blockSignals(True)
            rgn = self.baselineRgn.getRegion()
            self.ctrl.baselineStartSpin.setValue(rgn[0])
            self.ctrl.baselineEndSpin.setValue(rgn[1])
        except:
            raise
        finally:
            self.ctrl.baselineStartSpin.blockSignals(False)
            self.ctrl.baselineEndSpin.blockSignals(False)

    def baselineSpinChanged(self):
        try:
            self.baselineRgn.blockSignals(True)
            start = self.ctrl.baselineStartSpin.value()
            end = self.ctrl.baselineEndSpin.value()
            self.baselineRgn.setRegion((start, end))
        except:
            raise
        finally:
            self.baselineRgn.blockSignals(False)

    def pspRgnChanged(self):
        try:
            self.ctrl.pspStartSpin.blockSignals(True)
            self.ctrl.pspEndSpin.blockSignals(True)
            rgn = self.pspRgn.getRegion()
            self.ctrl.pspStartSpin.setValue(rgn[0])
            self.ctrl.pspEndSpin.setValue(rgn[1])
        except:
            raise
        finally:
            self.ctrl.pspStartSpin.blockSignals(False)
            self.ctrl.pspEndSpin.blockSignals(False)

    def pspSpinChanged(self):
        try:
            self.pspRgn.blockSignals(True)
            start = self.ctrl.pspStartSpin.value()
            end = self.ctrl.pspEndSpin.value()
            self.pspRgn.setRegion((start, end))
        except:
            raise
        finally:
            self.pspRgn.blockSignals(False)

    def healthRgnChanged(self):
        try:
            self.ctrl.healthStartSpin.blockSignals(True)
            self.ctrl.healthEndSpin.blockSignals(True)
            rgn = self.healthRgn.getRegion()
            self.ctrl.healthStartSpin.setValue(rgn[0])
            self.ctrl.healthEndSpin.setValue(rgn[1])
        except:
            raise
        finally:
            self.ctrl.healthStartSpin.blockSignals(False)
            self.ctrl.healthEndSpin.blockSignals(False)

    def healthSpinChanged(self):
        try:
            self.healthRgn.blockSignals(True)
            start = self.ctrl.healthStartSpin.value()
            end = self.ctrl.healthEndSpin.value()
            self.healthRgn.setRegion((start, end))
        except:
            raise
        finally:
            self.healthRgn.blockSignals(False)

    def analyze(self):
        for p in [self.plots.plasticityPlot, self.plots.RMP_plot, self.plots.RI_plot]:
            p.clear()

        if self.ctrl.averageAnalysisCheck.isChecked():
            times = self.averagedTraces['avgTimeStamp']
            traces = self.averagedTraces['avgData']
        else:
            times = self.traces['timestamp']
            traces = self.traces['data']

        self.analysisResults = np.zeros(len(traces), dtype=[('time', float), 
                                                            ('RMP', float), 
                                                            ('pspSlope', float),
                                                            ('pspAmplitude', float),
                                                            ('InputResistance', float)
                                                            ])

        self.analysisResults['time'] = times

        if self.ctrl.baselineCheck.isChecked():
            self.measureBaseline(traces)
            self.plots.RMP_plot.plot(x=times-self.expStart, y=self.analysisResults['RMP'], pen=None, symbol='o', symbolPen=None)

        if self.ctrl.pspCheck.isChecked():
            self.measurePSP(traces)
            if self.ctrl.measureModeCombo.currentText() == 'Slope (max)':
                self.plots.plasticityPlot.plot(x=times-self.expStart, y=self.analysisResults['pspSlope'], pen=None, symbol='o', symbolPen=None)
                base, basetime = (self.analysisResults['pspSlope'][:5].mean(), self.analysisResults['time'][:5].mean()-self.expStart)
                postStart = self.analysisResults['time'][5]
                postRgn = (np.argwhere(self.analysisResults['time'] > postStart+60*20.)[0], np.argwhere(self.analysisResults['time']< postStart+60*40.)[-1])
                post, postTime = (self.analysisResults['pspSlope'][postRgn[0]:postRgn[1]].mean(), self.analysisResults['time'][postRgn[0]:postRgn[1]].mean()-self.expStart)
                self.plots.plasticityPlot.plot(x=[basetime, postTime], y=[base, post], pen=None, symbolBrush='r')
                self.plots.plasticityPlot.setLabel('left', "Slope")
            elif self.ctrl.measureModeCombo.currentText() == 'Amplitude (max)':
                self.plots.plasticityPlot.plot(x=times-self.expStart, y=self.analysisResults['pspAmplitude'], pen=None, symbol='o', symbolPen=None)
                self.plots.plasticityPlot.setLabel('left', "Amplitude")
        if self.ctrl.healthCheck.isChecked():
            self.measureHealth(traces)
            self.plots.RI_plot.plot(x=times-self.expStart, y=self.analysisResults['InputResistance'], pen=None, symbol='o', symbolPen=None)

    def measureBaseline(self, traces):
        rgn = self.baselineRgn.getRegion()
        print "MeasureBaseline:"
        print "   ", traces[0].shape


        for i, trace in enumerate(traces):
            data = trace['primary']['Time':rgn[0]:rgn[1]]
            self.analysisResults[i]['RMP'] = data.mean()

    def measurePSP(self, traces):
        rgn = self.pspRgn.getRegion()
        timestep = traces[0].axisValues('Time')[1] - traces[0].axisValues('Time')[0]
        ptsToAvg = self.ctrl.measureAvgSpin.value()

        for i, trace in enumerate(traces):
            data = trace['primary']['Time':rgn[0]:rgn[1]]

            ## Measure PSP slope
            slopes = np.diff(data)
            maxSlopePosition = np.argwhere(slopes == slopes.max())[0]
            avgMaxSlope = slopes[maxSlopePosition-int(ptsToAvg/2):maxSlopePosition+int(ptsToAvg/2)].mean()/timestep
            self.analysisResults[i]['pspSlope'] = avgMaxSlope

            ## Measure PSP Amplitude
            if self.analysisResults['RMP'][i] != 0:
                baseline = self.analysisResults['RMP'][i]
            else:
                baseline = data[:5].mean() ## if we don't have a baseline measurement, just use the first 5 points
            peakPosition = np.argwhere(data == data.max())[0]
            avgPeak = data[peakPosition-int(ptsToAvg/2):peakPosition+int(ptsToAvg/2)].mean() - baseline
            self.analysisResults[i]['pspAmplitude'] = avgPeak

    def measureHealth(self, traces):
        rgn = self.healthRgn.getRegion()

        for i, trace in enumerate(traces):
            data = trace['Time':rgn[0]:rgn[1]]
            inputResistance = measureResistance(data, 'IC')[0]
            self.analysisResults[i]['InputResistance'] = inputResistance














    