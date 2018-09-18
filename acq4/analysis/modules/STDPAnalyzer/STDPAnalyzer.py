
from PyQt4 import QtGui, QtCore
from collections import OrderedDict
from acq4.analysis.AnalysisModule import AnalysisModule
import STDPControlTemplate, STDPPlotsTemplate
import acq4.pyqtgraph as pg
import numpy as np
from acq4.util.functions import measureResistance, measureResistanceWithExponentialFit
from acq4.util.DatabaseGui.DatabaseGui import DatabaseGui
import STDPFileLoader

class STDPAnalyzer(AnalysisModule):

    """This module analyzes features (such as stimulated PSPs, action potentials
    or responses to pulses) of repeated traces over time. It was originally 
    designed to analyze Spike-Timing Dependent Plasticity data."""

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

        self.pairingPlot = pg.PlotWidget()

        self.fileLoader = STDPFileLoader.STDPFileLoader(self.dataManager(), host=self, showFileTree=True)


        # ### Plots accessible through self.plots - defined above:
        #     exptPlot - displays the time when traces were recorded. Used to choose which traces are displayed in tracesPlot
        #     tracesPlot - displays data traces
        #     plasticityPlot - displays a measure of synaptic plasticity over the course of the experimetn
        #     RMP_plot - displays the resting membrane potential (or holding current) over the course of the Experiment
        #     RI_plot - displays the input resistance over the course of the experiment
        #     HoldingPlot -- displays the amount of slow holding current used over the course of the experiment

        self._elements_ = OrderedDict([
            ('File Loader', {'type':'ctrl', 'object': self.fileLoader, 'size': (100, 100)}),
            ('Control Panel', {'type':'ctrl', 'object': self.ctrlWidget, 'pos':('below', 'File Loader'),'size': (100, 400)}),
            ('Database', {'type':'ctrl', 'object': self.dbGui, 'pos':('below', 'Control Panel'), 'size':(100,100)}),
            ('EPSP Plots', {'type': 'ctrl', 'object': self.plotsWidget, 'pos': ('right', 'File Loader'), 'size': (400, 700)}),
            ('Pairing Plots', {'type': 'ctrl', 'object': self.pairingPlot, 'pos':('below', 'EPSP Plots')})
        ])
        self.initializeElements()
           
        
        ## Set labels/titles on plots  -- takes a lot of space
        # self.plots.exptPlot.setTitle('Experiment Timecourse')
        # self.plots.tracesPlot.setLabel('left', "Voltage") ### TODO: check whether traces are in VC or IC
        # self.plots.tracesPlot.setTitle("Data")
        self.plots.plasticityPlot.setLabel('left', 'Slope', units='V/s')
        # self.plots.plasticityPlot.setTitle('Plasticity')
        # self.plots.RMP_plot.setTitle('Resting Membrane Potential')
        self.plots.RMP_plot.setLabel('left', text='RMP', units='V')
        self.plots.RI_plot.setLabel('left', text='Input R', units='Ohm')
        self.plots.holdingPlot.setLabel('left', "Holding Current", units='A')
        # self.plots.RI_plot.setTitle('Input Resistance')

        for p in [self.plots.exptPlot, self.plots.tracesPlot, self.plots.plasticityPlot,
                 self.plots.RMP_plot, self.plots.RI_plot, self.plots.holdingPlot]:
            p.setLabel('bottom', 'Time', units='s')

        ## Set up measurement regions in plots
        self.traceSelectRgn = pg.LinearRegionItem()
        self.traceSelectRgn.setRegion([0, 300])
        self.plots.exptPlot.addItem(self.traceSelectRgn)
        self.traceSelectRgn.sigRegionChanged.connect(self.updateTracesPlot)

        self.plasticityRgn = pg.LinearRegionItem(movable=False)
        self.plasticityRgn.setRegion([27*60, 47*60])
        self.plots.exptPlot.addItem(self.plasticityRgn)

        self.baselineRgn = pg.LinearRegionItem(brush=(0,150,0,50))
        self.plots.tracesPlot.addItem(self.baselineRgn)
        
        self.pspRgn = pg.LinearRegionItem(brush=(150,0,0,50))
        self.plots.tracesPlot.addItem(self.pspRgn)

        self.healthRgn = pg.LinearRegionItem(brush=(0,0,150,50))
        self.plots.tracesPlot.addItem(self.healthRgn)

        self.pspLine = pg.InfiniteLine(pos=0.055, pen='b', movable=True)
        self.pairingPlot.addItem(self.pspLine)
        self.spikeLine = pg.InfiniteLine(pos=0.065, pen='r', movable=True)
        self.pairingPlot.addItem(self.spikeLine)
        self.ctrl.pspStartTimeSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=0.055, step=0.1)
        self.ctrl.spikePeakSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=0.065, step=0.1)
        self.pspLine.sigPositionChanged.connect(self.pspLineChanged)
        self.spikeLine.sigPositionChanged.connect(self.spikeLineChanged)
        self.ctrl.pspStartTimeSpin.valueChanged.connect(self.pspStartSpinChanged)
        self.ctrl.spikePeakSpin.valueChanged.connect(self.spikePeakSpinChanged)

        ### Connect control panel
        self.averageCtrl = pg.WidgetGroup(self.ctrl.traceDisplayGroup) ##TODO: save state when we save data
        self.ctrl.averageCheck.setChecked(True)
        self.ctrl.averageTimeSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=60, step=1)
        self.ctrl.averageNumberSpin.setOpts(step=1, dec=True)
        self.ctrl.startExcludeAPsSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=0, step=1, minstep=0.001)
        self.ctrl.endExcludeAPsSpin.setOpts(suffix='s', siPrefix=True, dec=True, value=0.25, step=1, minstep=0.001)
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
        self.ctrl.storeToDBBtn.clicked.connect(self.storeToDB)
        self.ctrl.createSummaryBtn.clicked.connect(self.summarySheetRequested)
        self.ctrl.createBlindSummaryBtn.clicked.connect(self.blindSummarySheetRequested)
        self.ctrl.defaultRgnBtn.clicked.connect(self.defaultBtnClicked)

        self.baselineRgn.setRegion((0,0.05))
        self.pspRgn.setRegion((0.052,0.067))
        self.healthRgn.setRegion((0.24,0.34))

        #self.ctrl.measureAvgSpin.setOpts(step=1, dec=True)
        self.ctrl.measureModeCombo.addItems(['Slope (max)'])

        ### Set up internal information storage
        self.traces = np.array([], dtype=[('timestamp', float), ('data', object)]) 
        self.excludedTraces = np.array([], dtype=[('timestamp', float), ('data', object)])
        self.averagedTraces = None
        self.resetAveragedTraces()
        self.lastAverageState = {}
        self.files = []
        self.analysisResults=None






    def loadEPSPFileRequested(self, files):
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
                self.lastAverageState = {}
                self.files.append(f)
        
        self.expStart = self.traces['timestamp'].min()
        self.averageCtrlChanged()
        self.updateExptPlot()
        self.updateTracesPlot()
        return True

    def loadPairingFileRequested(self, files):
        """Called by FileLoader when the load pairing file button is clicked, once for each selected file.
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
                self.pairingTraces = arr[:maxi]
                self.files.append(f)

        self.updatePairingPlot()
        return True

    def updateExptPlot(self):
        """Update the experiment plots with markers for the the timestamps of 
        all loaded EPSP traces, and averages (if selected in the UI)."""


        if len(self.traces) == 0:
            return

        self.plots.exptPlot.clear()
        self.plots.exptPlot.addItem(self.traceSelectRgn)

        if self.ctrl.averageCheck.isChecked():
            self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o', symbolSize=6, alpha=50)
            self.plots.exptPlot.plot(x=self.averagedTraces['avgTimeStamp']-self.expStart, y=[2]*len(self.averagedTraces), pen=None, symbol='o', symbolSize=6, symbolBrush=(255,0,0))
        else:
            self.plots.exptPlot.plot(x=self.traces['timestamp']-self.expStart, y=[1]*len(self.traces), pen=None, symbol='o', symbolSize=6)

        if self.ctrl.excludeAPsCheck.isChecked():
            self.plots.exptPlot.plot(x=self.excludedTraces['timestamp']-self.expStart, y=[1]*len(self.excludedTraces), pen=None, symbol='o', symbolSize=6, symbolBrush=(255,100,100))

    def clearTracesPlot(self):
        self.plots.tracesPlot.clear()
        for item in [self.baselineRgn, self.pspRgn, self.healthRgn]:
            self.plots.tracesPlot.addItem(item)

    def updateTracesPlot(self):
        """Update the Trace display plot to show the traces corresponding to
         the timestamps selected by the region in the experiment plot."""

        rgn = self.traceSelectRgn.getRegion()
        self.clearTracesPlot()

        ### plot all the traces with timestamps within the selected region (according to self.traceSelectRgn)
        if not self.ctrl.averageCheck.isChecked():
            data = self.traces[(self.traces['timestamp'] > rgn[0]+self.expStart)
                              *(self.traces['timestamp'] < rgn[1]+self.expStart)
                              ]['data']
            timeKey = 'timestamp'
            dataKey='data'
            for i, d in enumerate(data):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

        ### plot only the average traces with timestamps within the selected region
        else:
            data = self.averagedTraces[
                    (self.averagedTraces['avgTimeStamp'] > rgn[0]+self.expStart)
                   *(self.averagedTraces['avgTimeStamp'] < rgn[1]+self.expStart)]
            displayOrig = self.ctrl.displayTracesCheck.isChecked()
            timeKey = 'avgTimeStamp'
            dataKey='avgData'

            for i, d in enumerate(data['avgData']):
                self.plots.tracesPlot.plot(d['primary'], pen=pg.intColor(i, len(data)))

                ### also display the original traces if selected in the UI
                if displayOrig:
                    for t in data['origTimes'][i]:
                        orig = self.traces[self.traces['timestamp']==t]['data'][0]
                        self.plots.tracesPlot.plot(orig['primary'], pen=pg.intColor(i, len(data), alpha=30))

        ### If analysis has been done, mark the location on each trace where the highest slope was found
        if self.analysisResults is not None and len(data[dataKey] > 0):
            datatime = data[dataKey][0].axisValues('Time')
            timestep = datatime[1]-datatime[0]
            for i, time in enumerate(data[timeKey]):
                slopeTime = self.analysisResults[self.analysisResults['time'] == time]['highSlopeLocation']
                slopeInd = int(slopeTime/timestep)
                self.plots.tracesPlot.plot([slopeTime], [data[i][dataKey]['primary'][slopeInd]], pen=None, symbol='o', symbolPen=None, symbolBrush=pg.intColor(i, len(data)))

    def updatePairingPlot(self):
        self.pairingPlot.clear()
        avgTrace = self.pairingTraces[0]['data']['primary']-self.pairingTraces[0]['data']['primary'] ## get an empty array with the same structure as the data
        avgN = 0
        for i, trace in enumerate(self.pairingTraces):
            self.pairingPlot.plot(trace['data']['primary'])
            avgTrace += trace['data']['primary']
            avgN += 1

        self.avgPairingTrace = avgTrace/avgN
        self.pairingPlot.plot(self.avgPairingTrace, pen={'color':'r', 'width':2})

        self.pairingPlot.addItem(self.pspLine)
        self.pairingPlot.addItem(self.spikeLine)

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
            self.updateExptPlot()
            return

        self.getNewAverages()
        self.updateExptPlot()
        self.updateTracesPlot()

    def needNewAverage(self):
        ### Checks if the current values for the averaging controls are the same as when we last averaged
        excludeAPs = self.ctrl.excludeAPsCheck.isChecked()
        if not excludeAPs == self.lastAverageState.get('excludeAPs', None):
            return True

        if excludeAPs:
            start = self.ctrl.startExcludeAPsSpin.value()
            end = self.ctrl.endExcludeAPsSpin.value()
            if not ((start == self.lastAverageState.get('startExcludeAPsTime', None)) and (end == self.lastAverageState.get('endExcludeAPsTime', None))):
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
        start = self.ctrl.startExcludeAPsSpin.value()
        end = self.ctrl.endExcludeAPsSpin.value()

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

        self.lastAverageState = {'method': method, 'value': value, 'excludeAPs':excludeAPs, 'startExcludeAPsTime':start, 'endExcludeAPsTime':end}
        

    def checkForAP(self, trace, timeWindow):
        """Return True if there is an action potential present in the trace in the given timeWindow (tuple of start, stop)."""

        data = trace['primary']['Time':timeWindow[0]:timeWindow[1]]
        if data.max() > -0.02:
            return True
        else:
            return False

    def excludeAPs(self):
        timeWindow = (self.ctrl.startExcludeAPsSpin.value(), self.ctrl.endExcludeAPsSpin.value())
        APmask = np.zeros(len(self.traces), dtype=bool)
        for i, trace in enumerate(self.traces):
            APmask[i] = self.checkForAP(trace['data'], timeWindow)
        self.excludedTraces = self.traces[APmask]
        return self.traces[~APmask]

    def averageByTime(self, time, excludeAPs=False):
        n = int((self.traces['timestamp'].max() - self.expStart)/time) + ((self.traces['timestamp'].max() - self.expStart) % time > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)

        if excludeAPs:
            includedTraces = self.excludeAPs()
        else:
            includedTraces = self.traces

        t = 0 ## how many traces we've gone through
        i = 0 ## how many timesteps we've gone through
        while t < len(includedTraces):
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
                continue

            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            
            t += len(traces)
            i += 1

        self.averagedTraces = self.averagedTraces[self.averagedTraces['avgTimeStamp'] != 0] ## clean up any left over zeros from pauses in data collection


    def averageByNumber(self, number, excludeAPs=False):
        n = int(len(self.traces)/number) + (len(self.traces) % number > 0) ### weird solution for rounding up
        self.resetAveragedTraces(n)

        if excludeAPs:
            includedTraces = self.excludeAPs()
        else:
            includedTraces = self.traces

        t = 0
        i = 0
        while t < len(includedTraces):
            traces = includedTraces[i*number:i*number+number]

            x = traces[0]['data']
            for t2 in traces[1:]:
                x += t2['data']
            x /= float(len(traces))

            self.averagedTraces[i]['avgTimeStamp'] = traces['timestamp'].mean()
            self.averagedTraces[i]['avgData'] = x
            self.averagedTraces[i]['origTimes'] = list(traces['timestamp'])
            t += len(traces)
            i += 1

        self.averagedTraces = self.averagedTraces[self.averagedTraces['avgTimeStamp'] != 0] ## clean up any left over zeros from pauses in data collection

    def defaultBtnClicked(self):
        self.ctrl.plasticityRgnStartSpin.setValue(27.0)
        self.ctrl.plasticityRgnEndSpin.setValue(47.0)

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


    def pspLineChanged(self):
        try:
            self.ctrl.pspStartTimeSpin.blockSignals(True)
            pos = self.pspLine.value()
            self.ctrl.pspStartTimeSpin.setValue(pos)
        except:
            raise
        finally:
            self.ctrl.pspStartTimeSpin.blockSignals(False)

    def pspStartSpinChanged(self):
        try:
            self.pspLine.blockSignals(True)
            value = self.ctrl.pspStartTimeSpin.value()
            self.pspLine.setPos(value)
        except:
            raise
        finally:
            self.pspLine.blockSignals(False)

    def spikeLineChanged(self):
        try:
            self.ctrl.spikePeakSpin.blockSignals(True)
            pos = self.spikeLine.value()
            self.ctrl.spikePeakSpin.setValue(pos)
        except:
            raise
        finally:
            self.ctrl.spikePeakSpin.blockSignals(False)

    def spikePeakSpinChanged(self):
        try:
            self.spikeLine.blockSignals(True)
            value = self.ctrl.spikePeakSpin.value()
            self.spikeLine.setPos(value)
        except:
            raise
        finally:
            self.spikeLine.blockSignals(False)

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
                                                            ('slopeFitOffset', float),
                                                            ('highSlopeLocation', float),
                                                            ('pspAmplitude', float),
                                                            ('inputResistance', float),
                                                            ('holdingCurrent',float),
                                                            ('bridgeBalance', float),
                                                            ('tau', float)
                                                            ])

        self.analysisResults['time'] = times
        
        symsize = 5.0
        
        if self.ctrl.healthCheck.isChecked():
            self.measureHealth(traces)
            self.plots.RI_plot.plot(x=times-self.expStart, y=self.analysisResults['inputResistance'],
                pen=None, symbol='o', symbolSize=symsize, symbolPen=None)

        if self.ctrl.baselineCheck.isChecked():
            self.measureBaseline(traces)
            self.plots.RMP_plot.plot(x=times-self.expStart, y=self.analysisResults['RMP'],
                pen=None, symbol='o', symbolSize=symsize, symbolPen=None)

        self.measureCurrent(traces)
        self.plots.holdingPlot.plot(x=times-self.expStart, y=self.analysisResults['holdingCurrent'],
            pen=None, symbol='o', symbolSize=symsize, symbolPen=None)

        postwin = [self.ctrl.plasticityRgnStartSpin.value(), self.ctrl.plasticityRgnEndSpin.value()]
        #postwin = [20., 40.]  # minutes after start for measuring amplitude
        #postwin = [27., 47.] ## Accounted for below in postStart --minutes after start (of pre-pairing baseline) for measuring post-pairing amplitude. assumes baseline + pairing takes 7 minutes
        if self.ctrl.pspCheck.isChecked():
            self.measurePSP(traces)
            if self.ctrl.measureModeCombo.currentText() == 'Slope (max)':
                self.plots.plasticityPlot.plot(x=times-self.expStart, y=self.analysisResults['pspSlope'],
                    pen=None, symbol='o', symbolSize=symsize, symbolPen=None)
                #basepts = self.analysisResults['time'].shape[0]-1 ## Paul, why did you choose this?
                basepts = 5 ## there should be 5 traces in the baseline
                
                base, basetime = (self.analysisResults['pspSlope'][:basepts].mean(),
                    [self.analysisResults['time'][:basepts][0]-self.expStart, self.analysisResults['time'][:basepts][-1]-self.expStart])
                #postStart = self.analysisResults['time'][0]+ 7*60 ## baseline and pairing take up 7 minutes from the start of the experiment
                pr1 = np.argwhere(self.analysisResults['time'] >= 60*postwin[0]+self.expStart)
                pr2 = np.argwhere(self.analysisResults['time'] <= 60*postwin[1]+self.expStart)
                try:
                    x = pr1[0] # no points inside 
                except:
                    print self.analysisResults['time']
                    print 'starttime: ', postStart
                    msg = 'Recording is shorter than needed for analysis window\n'
                    msg += 'Max rec time: %8.3f sec, window starts at %8.3f sec' % (np.max
                        (self.analysisResults['time']), 60.*postwin[0])
                    raise ValueError(msg)
                    return
                postRgn = (pr1[0], pr2[-1])
                post, postTime = (self.analysisResults['pspSlope'][postRgn[0]:postRgn[1]].mean(),
                    [self.analysisResults['time'][postRgn[0]][0]-self.expStart, self.analysisResults['time'][postRgn[1]][0]-self.expStart])
                self.plots.plasticityPlot.plot(x=basetime, y=[base]*2, pen='r')
                self.plots.plasticityPlot.plot(x=postTime, y=[post]*2, pen='r')
                self.plasticity = post/base
                self.plots.plasticityPlot.setLabel('left', "EPSP Slope (mV/ms)")
            elif self.ctrl.measureModeCombo.currentText() == 'Amplitude (max)':
                self.plots.plasticityPlot.plot(x=times-self.expStart, y=self.analysisResults['pspAmplitude'],
                    pen=None, symbol='o', symbolSize=symsize, symbolPen=None)
                self.plots.plasticityPlot.setLabel('left', "EPSP Amplitude (mV)")
        self.updateTracesPlot()

    def measureBaseline(self, traces):
        rgn = self.baselineRgn.getRegion()
        for i, trace in enumerate(traces):
            data = trace['primary']['Time':rgn[0]:rgn[1]]
            self.analysisResults[i]['RMP'] = data.mean()

    def measureCurrent(self, traces):
        for i, trace in enumerate(traces):
            self.analysisResults[i]['holdingCurrent'] = trace['secondary'].mean()

    def measurePSP(self, traces):
        rgn = self.pspRgn.getRegion()
        timestep = traces[0].axisValues('Time')[1] - traces[0].axisValues('Time')[0]
        #ptsToAvg = self.ctrl.measureAvgSpin.value()

        for i, trace in enumerate(traces):
            data = trace['Time':rgn[0]:rgn[1]]
            rgn2 = (data.axisValues('Time')[0], data.axisValues('Time')[-1])

            ## Measure PSP slope -- takes max diff between points
            # slopes = np.diff(data)
            # maxSlopePosition = np.argwhere(slopes == slopes.max())[0]
            # avgMaxSlope = slopes[maxSlopePosition-int(ptsToAvg/2):maxSlopePosition+int(ptsToAvg/2)].mean()/timestep
            # self.analysisResults[i]['pspSlope'] = avgMaxSlope

            ## Measure PSP slope -- does a rolling fit of a line
            step = int(0.0001/timestep) ## measure every 100 us
            region = int(0.0003/timestep) ## fit a line to a 300 us region
            t = region
            slope = 0
            highest=None
           
            while t < len(data['primary']):
                data2 = data['Time':t-region:t]['primary']
                s = np.polyfit(np.arange(len(data2))*timestep, data2, 1)
                if s[0] > slope:
                    slope = s[0]
                    offset = s[1]
                    hightime = rgn2[0]+t*timestep-(region*timestep)/2.
                t += step

            self.analysisResults[i]['pspSlope'] = slope
            self.analysisResults[i]['slopeFitOffset'] = offset
            self.analysisResults[i]['highSlopeLocation'] = hightime



            # # Measure PSP Amplitude
            # if self.analysisResults['RMP'][i] != 0:
            #     baseline = self.analysisResults['RMP'][i]
            # else:
            #     baseline = data['primary'][:5].mean() ## if we don't have a baseline measurement, just use the first 5 points
            # peakPosition = np.argwhere(data['primary'] == data['primary'].max())[0]
            # avgPeak = data['primary'][peakPosition-int(5/2):peakPosition+int(5/2)].mean() - baseline

            # self.analysisResults[i]['pspAmplitude'] = avgPeak

    def measureHealth(self, traces):
        rgn = self.healthRgn.getRegion()

        for i, trace in enumerate(traces):
            data = trace['Time':rgn[0]:rgn[1]]
            R = measureResistanceWithExponentialFit(data, debug=False)
            self.analysisResults[i]['inputResistance'] = R['inputResistance']
            self.analysisResults[i]['tau'] = R['tau']
            bridgeCompensation = self.dataModel.getBridgeBalanceCompensation(trace)
            self.analysisResults[i]['bridgeBalance'] = bridgeCompensation + R['bridgeBalance']

    def storeToDB(self):
        self.storeTrialsToDB()
        self.storeCellInfoToDB()

    def storeTrialsToDB(self):
        if len(self.analysisResults) == 0:
            self.analyze()

        db = self.dbGui.getDb()
        if db is None:
            raise Exception("No database loaded.")
        
        table = self.dbGui.getTableName(self.dbIdentity+'.trials')

        trialFields = OrderedDict([
            ('CellDir', 'directory:Cell'),
            ('ProtocolSequenceDir', 'directory:ProtocolSequence'),
            ('timestamp', 'real'),
            ('time', 'real'),
            ('RMP', 'real'),
            ('inputResistance', 'real'),
            ('tau', 'real'),
            ('bridgeBalance', 'real'),
            ('pspSlope', 'real'),
            ('normalizedPspSlope', 'real'),
            ('slopeFitOffset', 'real'),
            ('highSlopeLocation', 'real'),
            ('pspAmplitude', 'real'),
            ('pspRgnStart', 'real'),
            ('pspRgnEnd', 'real'),
            ('analysisCtrlState', 'text'),
            ('averageCtrlState', 'text'),
            ('includedProtocols', 'text')
            ])

        db.checkTable(table, owner=self.dbIdentity+'.trials', columns=trialFields, create=True, addUnknownColumns=True, indexes=[['CellDir'], ['ProtocolSequenceDir']])


        data = np.zeros(len(self.analysisResults), dtype=[
                                                            ('CellDir', object),
                                                            #('ProtocolSequenceDir', object),
                                                            ('timestamp', float), 
                                                            ('time', float),
                                                            ('RMP', float), 
                                                            ('inputResistance', float),
                                                            ('tau', float),
                                                            ('bridgeBalance', float)
                                                            ('pspSlope', float),
                                                            ('normalizedPspSlope', float),
                                                            ('slopeFitOffset', float),
                                                            ('highSlopeLocation', float),
                                                            ('pspAmplitude', float),
                                                            ('pspRgnStart', float),
                                                            ('pspRgnEnd', float),
                                                            ('analysisCtrlState', object),
                                                            ('averageCtrlState', object),
                                                            ('includedProtocols', object)
                                                            ])

        data['CellDir'] = self.dataModel.getParent(self.files[0], 'Cell')
        data['pspRgnStart'] = self.pspRgn.getRegion()[0]
        data['pspRgnEnd'] = self.pspRgn.getRegion()[1]
        data['analysisCtrlState'] = str(self.analysisCtrl.state())
        data['averageCtrlState'] = str(self.averageCtrl.state())

        baselineSlope = self.analysisResults[self.analysisResults['time'] < self.expStart+300]['pspSlope'].mean()
        for i in range(len(self.analysisResults)):
            data[i]['timestamp'] = self.analysisResults[i]['time']
            data[i]['time'] = self.analysisResults[i]['time'] - self.expStart
            data[i]['RMP'] = self.analysisResults[i]['RMP']
            data[i]['inputResistance'] = self.analysisResults[i]['inputResistance']
            data[i]['pspSlope'] = self.analysisResults[i]['pspSlope']
            data[i]['normalizedPspSlope'] = self.analysisResults[i]['pspSlope']/baselineSlope
            data[i]['slopeFitOffset'] = self.analysisResults[i]['slopeFitOffset']
            data[i]['highSlopeLocation'] = self.analysisResults[i]['highSlopeLocation']
            data[i]['pspAmplitude'] = self.analysisResults[i]['pspAmplitude']
            data[i]['includedProtocols'] = self.averagedTraces[i]['origTimes'] ### TODO: make this protocolDirs instead of timestamps....

        old = db.select(table, where={'CellDir':data['CellDir'][0]}, toArray=True)
        if old is not None: ## only do deleting if there is already data stored for this cell
            db.delete(table, where={'CellDir': data['CellDir'][0]})
        
        db.insert(table, data)

    def storeCellInfoToDB(self):
        db = self.dbGui.getDb()
        if db is None:
            raise Exception("No database loaded.")
        
        table = self.dbGui.getTableName(self.dbIdentity+'.cell')

        cellFields = OrderedDict([
            ('CellDir', 'directory:Cell'),
            ('plasticity', 'real'),
            ('pspTime', 'real'),
            ('firstSpikeTime', 'real'),
            ('pairingInterval', 'real'),
            ('bath_drug', 'text'),
            ('challenge_drug', 'text'),
            ])

        db.checkTable(table, owner=self.dbIdentity+'.cell', columns=cellFields, create=True, addUnknownColumns=True, indexes=[['CellDir']])

        cell = self.dataModel.getParent(self.files[0], 'Cell')
        record = {}
        record['CellDir'] = cell
        record['plasticity'] = self.plasticity
        record['pspTime'] = self.ctrl.pspStartTimeSpin.value()
        record['firstSpikeTime'] = self.ctrl.spikePeakSpin.value()
        record['pairingInterval'] = record['firstSpikeTime'] - record['pspTime']
        record['bath_drug'] = cell.info().get('antagonist_code', '')
        record['challenge_drug'] = cell.info().get('agonist_code', '')

        old = db.select(table, where={'CellDir':cell}, toArray=True)
        if old is not None: ## only do deleting if there is already data stored for this cell
            db.delete(table, where={'CellDir': cell})

        db.insert(table, record)


    def summarySheetRequested(self):
        self.summaryView = self.createSummarySheet()
        self.summaryView.show()

    def blindSummarySheetRequested(self):
        self.summaryView = self.createSummarySheet(showPlasticity=False)
        self.summaryView.show()

    def createSummarySheet(self, showPlasticity=True):
        view = pg.GraphicsView()
        l = pg.GraphicsLayout()
        view.setCentralItem(l)

        cell = self.dataModel.getParent(self.files[0], 'Cell')

        if self.dbGui.getDb() is not None:
            cellName = cell.name(relativeTo=self.dbGui.getDb().baseDir())
        else:
            raise Exception('No database loaded.')
        l.addLabel(text=cellName, bold=True, colspan=3, size='14pt')

        ### Add average PSP traces
        APmask = np.zeros(len(self.traces), dtype=bool)
        for i, trace in enumerate(self.traces):
            APmask[i] = self.checkForAP(trace['data'], (0, 0.25))
        includedTraces = self.traces[~APmask]

        baseTraceSum = np.zeros(len(self.traces[0]['data']['primary']))
        baseTraceNumber = 0

        postTraceSum = np.zeros(len(self.traces[0]['data']['primary']))
        postTraceNumber = 0

        for trace in includedTraces:
            time = trace['timestamp'] - self.expStart
            if time < 310:
                baseTraceSum += trace['data']['primary']
                baseTraceNumber += 1
            elif time > 27*60 and time < 47*60: ## 20-40 minutes post-pairing
                postTraceSum += trace['data']['primary']
                postTraceNumber += 1

        baseAvg = baseTraceSum/float(baseTraceNumber)
        postAvg = postTraceSum/float(postTraceNumber)
        timeValues = self.traces[0]['data']['primary'].axisValues('Time')
        rate = timeValues[1] - timeValues[0]

        plot = pg.PlotItem(title='Average PSPs', labels={'left': 'V', 'bottom':'time'})
        plot.addLegend()
        plot.plot(x=timeValues[0.045/rate:0.085/rate], y=baseAvg[0.045/rate:0.085/rate], pen='b', name='Baseline')
        if showPlasticity:
            plot.plot(x=timeValues[0.045/rate:0.085/rate], y=postAvg[0.045/rate:0.085/rate], pen='r', name='Post-pairing')
        
        l.addItem(plot, row=1, col=0, rowspan=2)

        ### add label about drugs, info, etc...
        agonist = cell.info().get('agonist_code', 'No info')
        antagonist = cell.info().get('antagonist_code', 'No info')

        preNotes = 'Notes: ' + cell.info().get('notes', '')
        i=30
        notes=''
        while i< len(preNotes)+30:
            notes += preNotes[i-30:i]+"<br />     "
            i += 30

        if showPlasticity:
            plasticity='%g %%' % (self.plasticity * 100.)
        else:
            plasticity="Not shown"

        interval = self.ctrl.spikePeakSpin.value() - self.ctrl.pspStartTimeSpin.value()
        
        info = "Antagonist: %s <br /> Agonist: %s <br /><br />Pairing Interval: %f<br /><br /> Plasticity: %s" % (antagonist, agonist, interval, plasticity)
        l.addLabel(text=info, row=1, col=2)
        l.addLabel(text=notes, row=2, col=2)

        pairingPlot = pg.PlotItem()
        pairingPlot.plot(timeValues[0.05/rate:0.15/rate], self.avgPairingTrace['Time':0.05:0.15])
        l.addItem(pairingPlot, row=1, col=1, rowspan=2)
        

        
        plasticityPlot = pg.PlotItem(x=self.analysisResults['time']-self.expStart, y=self.analysisResults['pspSlope'],
            pen=None, symbol='o', symbolSize=5, symbolBrush='w')
        plasticityPlot.setYRange(0, 4)
        plasticityPlot.setXRange(-50, 3200)
        if showPlasticity:
            l.addItem(plasticityPlot, row=4, col=0, colspan=3)
       
        rmpPlot = pg.PlotItem(x=self.analysisResults['time']-self.expStart, y=self.analysisResults['RMP'],
            pen=None, symbol='o', symbolSize=5, symbolBrush='w')
        rmpPlot.setYRange(-0.080, -0.030)
        rmpPlot.setXRange(-50, 3200)
        l.addItem(rmpPlot, row=5, col=0, colspan=3)

        riPlot = pg.PlotItem(x=self.analysisResults['time']-self.expStart, y=self.analysisResults['inputResistance'],
            pen=None, symbol='o', symbolSize=5, symbolBrush='w')
        riPlot.setYRange(0, 300e6)
        riPlot.setXRange(-50, 3200)
        l.addItem(riPlot, row=6, col=0, colspan=3)

        holdingPlot = pg.PlotItem(x=self.analysisResults['time']-self.expStart, y=self.analysisResults['holdingCurrent'],
            pen=None, symbol='o', symbolSize=5, symbolBrush='w' )
        holdingPlot.setYRange(-400e-12, 50e-12)
        holdingPlot.setXRange(-50, 3200)
        l.addItem(holdingPlot, row=7, col=0, colspan=3)

        plasticityPlot.setLabel('left', 'PSP Slope')
        rmpPlot.setLabel('left', 'RMP', units='V')
        riPlot.setLabel('left', 'Ri', units='Ohm')
        holdingPlot.setLabel('left', 'Holding Current', units='A')


        return view


        





    