from __future__ import print_function
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import numpy as np
import scipy
import acq4.util.functions as fn
from . import CellHealthCtrlTemplate
from acq4.util.HelpfulException import HelpfulException
from acq4.pyqtgraph.widgets.FileDialog import FileDialog
import sys


class CellHealthTracker(AnalysisModule):
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlWidget = Qt.QWidget()
        self.ctrl = CellHealthCtrlTemplate.Ui_widget()
        self.ctrl.setupUi(self.ctrlWidget)
        self.ctrlStateGroup = pg.WidgetGroup(self.ctrlWidget)
        
        self.ctrl.startSpin.setOpts(step=0.05, suffix='s', siPrefix=True, value=0.35, dec=False)
        self.ctrl.stopSpin.setOpts(step=0.05, suffix='s', siPrefix=True, value=0.5, dec=False)
        
        ## Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (100, 300), 'host': self, 'args': {'showFileTree': True}}),
            ('ctrl', {'type': 'ctrl', 'object': self.ctrlWidget, 'pos': ('bottom', 'File Loader'), 'size': (100, 100)}),
            ('Rs Plot', {'type': 'plot', 'pos':('right', 'File Loader'), 'size':(200, 600), 'labels':{'left':(None,'Ohms'), 'bottom':(None,'s')}}),
            ('Rm Plot', {'type': 'plot', 'pos':('bottom', 'Rs Plot'), 'size':(200, 600),'labels':{'left':(None,'Ohms'), 'bottom':(None,'s')}}),
            ('Ih Plot', {'type': 'plot', 'pos':('bottom', 'Rm Plot'), 'size':(200, 600), 'labels':{'left':(None,'A'), 'bottom':(None, 's')}}),
            ('Traces Plot', {'type': 'plot', 'pos':('right', 'ctrl'), 'size':(200, 600), 'labels':{'left':(None,'A'), 'bottom':(None,'s')}}),
        ])
        self.initializeElements()
        for el in self.getAllElements():
            self.getElement(el, create=True)
            
        
        self.tracesPlot = self.getElement('Traces Plot')
        self.measurementArray = np.zeros(1000, dtype=[
            ('unixtime', float),
            ('time', float),
            ('Rs', float),
            ('Rm', float),
            ('Ih', float)
        ])                  
        
        self.files = {} ## keys are dhs, values are {'data': array of time/Rs/Rm/Ih, 'ctrlState': state, 'traces': clampData}
        
        self.ctrl.processBtn.clicked.connect(self.processClicked)
        self.ctrl.saveBtn.clicked.connect(self.saveClicked)

    def loadFileRequested(self, dhList):
        """Called by file loader when a file load is requested."""
        ## return True if file loads successfully, else return False
        
        try:
            for dh in dhList:
                #if dh.name is "Patch":
                    #pass
                if dh is None:
                    continue
                if dh.isDir():
                    self.files[dh] = {}
                    #self.files[dh]['traces']=[]
                    #traces = []
                    self.tracesPlot.clear()
                    i = 0
                    limitTraces=False
                    if len(dh.subDirs()) > 80:
                        limitTraces=True
                    for f in dh.subDirs():
                        if i==0 or i%20==0 or not limitTraces:
                            fh = self.dataModel.getClampFile(dh[f])
                            if fh is not None:
                                self.loadClampData(fh, dh, plot=True)
                            else:
                                break ## assume that once we get one empty protocolDir, all the following ones will be empty too
                        i+=1
            return True
        except:
            raise
        
    def processClicked(self):
        ## read all the traces from the selected file
        dh = self.getElement("File Loader").selectedFile()
        if dh.isDir():
            traces = []
            for f in dh.subDirs():
                fh = self.dataModel.getClampFile(dh[f])
                if fh is not None:
                    trace = self.loadClampData(fh, dh, plot=False)
                    traces.append(trace)
            
        ## hand list of traces to self.process sequence
        self.processSequence(traces, dh)
    
        
    def loadClampData(self, f, dh, plot=True):
        try:
            data = f.read()
        except:
            print(f)
            raise
        #print f.info()
        time = f.info()['__timestamp__']
        #self.files[dh]['traces'].append((data, time))
        if plot:
            self.tracesPlot.plot(data['Channel':'primary'])
        return (data, time)
        
        
    def processSequence(self, traces, dh=None):
        if dh is None:
            dh = self.getElement("File Loader").selectedFile()
        
        #self.files[dh]['data'] = np.zeros(len(self.files[dh]['traces']), dtype=self.measurementArray.dtype)
        self.files[dh]['data'] = np.zeros(len(traces), dtype=self.measurementArray.dtype)
        
        #for i, (data, time) in enumerate(self.files[dh]['traces']):
        for i, (data, time) in enumerate(traces):
            stats = self.measureParams(data)
            stats['unixtime'] = time
            self.files[dh]['data'][i] = stats
            
        self.updatePlots()
            
    
    def updatePlots(self):
        i = len(self.measurementArray)
        dtype = self.measurementArray.dtype
        self.measurementArray = np.zeros(i, dtype=dtype)
        
        count = 0
        for dh in self.files:
            data = self.files[dh].get('data', np.zeros(0, dtype=dtype))
            if len(data) > len(self.measurementArray)-count:
                self.extendMeasurementArray()
            self.measurementArray[count:count+len(data)] = data
            count += len(data)
            
        self.measurementArray.sort(order='unixtime')
        self.measurementArray['time'] = self.measurementArray['unixtime']-self.measurementArray[self.measurementArray['unixtime'] != 0]['unixtime'].min()
        
        arr = self.measurementArray[self.measurementArray['unixtime'] != 0]
        for x in ['Rs', 'Rm', 'Ih']:
            p = self.getElement(x+' Plot')
            p.clear()
            p.plot(arr['time'], arr[x])
            
        self.currentData = arr
            
    def extendMeasurementArray(self):
        i = len(self.measurementArray)
        arr = np.zeros(i+1000, dtype=self.measurementArray.dtype)
        arr[0:i] = self.measurementArray
        self.measurementArray = arr
        
    def saveClicked(self):
        self.saveMA()
        
    def saveMA(self, fileName=None):
        if fileName is None:
            dh = self.getElement("File Loader").baseDir().name()
            self.fileDialog = FileDialog(None, "Save traces", dh, '*.ma')
            self.fileDialog.setAcceptMode(Qt.QFileDialog.AcceptSave)
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.saveMA)
            return  
        
        #arr = MetaArray(self.currentData) ### need to format this with axes and info
        arr = MetaArray([self.currentData['Rs'], self.currentData['Rm'], self.currentData['Ih']], info=[
            {'name':'vals', 'cols':[
                {'name':'Rs', 'units':'Ohms'},
                {'name':'Rm', 'units':'Ohms'},
                {'name':'Ih', 'units':'A'}]},
            {'name':'time', 'units':'s', 'values':self.currentData['time']}]) 
        
        arr.write(fileName)
        
            
        
    def measureParams(self, data, display=None):
        cmd = data['command']['Time':self.ctrl.startSpin.value():self.ctrl.stopSpin.value()]
        #data = waveform['primary']['Time':self.ctrls['start'].value():self.ctrls['stop'].value()]
        #print np.argwhere(cmd != cmd[0])
        pulseStart = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[0][0]]
        pulseStop = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[-1][0]]
        
        #print "\n\nAnalysis parameters:", params
        ## Extract specific time segments
        nudge = 0.1e-3
        base = data['Time': :(pulseStart-nudge)]
        pulse = data['Time': (pulseStart+nudge):(pulseStop-nudge)]
        pulseEnd = data['Time': pulseStart+((pulseStop-pulseStart)*2./3.):pulseStop-nudge]
        end = data['Time': (pulseStop+nudge): ]
        #print "time ranges:", pulse.xvals('Time').min(),pulse.xvals('Time').max(),end.xvals('Time').min(),end.xvals('Time').max()
        pulseAmp = pulse['command'].mean() - base['command'].mean()
        
        method = str(self.ctrl.methodCombo.currentText())
        #print method
        if method == "Simple Ohm's law":
            print('using simple method')
            if pulseAmp < 0:
                RsPeak = data['primary'].min()
            else:
                RsPeak = data['primary'].max()
            aRes = pulseAmp/(RsPeak-base['primary'].mean())
            iRes = pulseAmp/(pulseEnd['primary'].mean() - base['primary'].mean())
            rmc = base['primary'].mean()
            
        elif method in ['Santos-Sacchi raw', 'Santos-Sacchi fit']:
            ### Exponential fit
            ##  v[0] is offset to start of exp
            ##  v[1] is amplitude of exp
            ##  v[2] is tau
            def expFn(v, t):
                return (v[0]-v[1]) + v[1] * np.exp(-t / v[2])
            
            ## predictions
            ar = 10e6
            ir = 200e6
            #if self.ctrls['mode'].currentText() == 'VC':
            if True: ## Always want it to use VC settings for now
                ari = pulseAmp / ar
                iri = pulseAmp / ir
                pred1 = [ari, ari-iri, 1e-3]
                pred2 = [iri-ari, iri-ari, 1e-3]
            else:
                #clamp = self.manager.getDevice(self.clampName)
                try:
                    bridge = data._info[-1]['ClampState']['ClampParams']['BridgeBalResist']
                    bridgeOn = data._info[-1]['ClampState']['ClampParams']['BridgeBalEnabled']
                    #bridge = float(clamp.getParam('BridgeBalResist'))  ## pull this from the data instead.
                    #bridgeOn = clamp.getParam('BridgeBalEnable')
                    if not bridgeOn:
                        bridge = 0.0
                except:
                    bridge = 0.0
                #print "bridge:", bridge
                arv = pulseAmp * ar - bridge
                irv = pulseAmp * ir
                pred1 = [arv, -irv, 10e-3]
                pred2 = [irv, irv, 50e-3]
                
            ## Fit exponential to pulse and post-pulse traces
            tVals1 = pulse.xvals('Time')-pulse.xvals('Time').min()
            tVals2 = end.xvals('Time')-end.xvals('Time').min()
            
            baseMean = base['primary'].mean()
            fit1 = scipy.optimize.leastsq(
                lambda v, t, y: y - expFn(v, t), pred1, 
                args=(tVals1, pulse['primary'] - baseMean),
                maxfev=200, full_output=1)
            #fit2 = scipy.optimize.leastsq(
                #lambda v, t, y: y - expFn(v, t), pred2, 
                #args=(tVals2, end['primary'] - baseMean),
                #maxfev=200, full_output=1, warning=False)
                
            
            #err = max(abs(fit1[2]['fvec']).sum(), abs(fit2[2]['fvec']).sum())
            err = abs(fit1[2]['fvec']).sum()
            
            
            ## Average fit1 with fit2 (needs massaging since fits have different starting points)
            #print fit1
            fit1 = fit1[0]
            #fit2 = fit2[0]
            #fitAvg = [   ## Let's just not do this.
                #0.5 * (fit1[0] - (fit2[0] - (fit1[0] - fit1[1]))),
                #0.5 * (fit1[1] - fit2[1]),
                #0.5 * (fit1[2] + fit2[2])            
            #]
            fitAvg = fit1
    
            (fitOffset, fitAmp, fitTau) = fit1
            #print fit1
            
            fitTrace = np.empty(len(data))
            
            ## Handle analysis differently depending on clamp mode
            #if self.ctrls['mode'].currentText() == 'VC':
            if True: ## Always use VC mode for now
                iBase = base['Channel': 'primary']
                iPulse = pulse['Channel': 'primary'] 
                iPulseEnd = pulseEnd['Channel': 'primary'] 
                vBase = base['Channel': 'command']
                vPulse = pulse['Channel': 'command'] 
                vStep = vPulse.mean() - vBase.mean()
                sign = [-1, 1][vStep > 0]
    
                iStep = sign * max(1e-15, sign * (iPulseEnd.mean() - iBase.mean()))
                iRes = vStep / iStep
                
                #### From Santos-Sacchi 1993:
                ## 1. compute charge transfered during the charging phase 
                pTimes = pulse.xvals('Time')
                iCapEnd = pTimes[-1]
                iCap = iPulse['Time':pTimes[0]:iCapEnd] - iPulseEnd.mean()
                
                ## Instead, we will use the fit to guess how much charge transfer there would have been 
                ## if the charging curve had gone all the way back to the beginning of the pulse
                if method == "Santos-Sacchi fit":
                    iCap = expFn((fit1[1],fit1[1],fit1[2]), np.linspace(0, iCapEnd-pTimes[0], iCap.shape[0]))  
                
                Q = sum(iCap) * (iCapEnd - pTimes[0]) / iCap.shape[0]
                
                
                Rin = iRes
                Vc = vStep
                Rs_denom = (Q * Rin + fitTau * Vc)
                if Rs_denom != 0.0:
                    Rs = (Rin * fitTau * Vc) / Rs_denom
                    Rm = Rin - Rs
                    Cm = (Rin**2 * Q) / (Rm**2 * Vc)
                else:
                    Rs = 0
                    Rm = 0
                    Cm = 0
                aRes = Rs
                cap = Cm
                
            #if self.ctrls['mode'].currentText() == 'IC':
            if False: ## ic measurements not yet supported in ui
                iBase = base['Channel': 'command']
                iPulse = pulse['Channel': 'command'] 
                vBase = base['Channel': 'primary']
                vPulse = pulse['Channel': 'primary'] 
                vPulseEnd = pulseEnd['Channel': 'primary'] 
                iStep = iPulse.mean() - iBase.mean()
                
                if iStep >= 0:
                    vStep = max(1e-5, -fitAmp)
                else:
                    vStep = min(-1e-5, -fitAmp)
               
                if iStep == 0:
                    iStep = 1e-14
                    
                iRes = (vStep / iStep)
                aRes = (fitOffset / iStep) + bridge
                cap = fitTau / iRes
                
                
            rmp = vBase.mean()
            rmps = vBase.std()
            rmc = iBase.mean()
            rmcs = iBase.std()
            ##print rmp, rmc
        
        ## use ui to determine which stats to return
        stats = np.zeros((1,), dtype=self.measurementArray.dtype)
        
        if self.ctrl.RsCheck.isChecked():
            stats['Rs'] = aRes
        if self.ctrl.RmCheck.isChecked():
            stats['Rm'] = iRes
        #if self.ctrls['Capacitance'].isChecked():
            #stats['Capacitance'] = cap
        if self.ctrl.IhCheck.isChecked():
            stats['Ih'] = rmc
        #if self.ctrls['FitError'].isChecked():
            #stats['FitError'] = err
        #if self.ctrls['RestingPotential'].isChecked():
            #stats['RestingPotential'] = rmp

        return stats   
