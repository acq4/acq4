# -*- coding: utf-8 -*-
from PatchTemplate import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
from lib.util.WidgetGroup import WidgetGroup
from lib.util.PlotWidget import PlotWidget
from lib.util.MetaArray import *
import traceback, sys, time
from numpy import *
import scipy.optimize

class PatchWindow(QtGui.QMainWindow):
    def __init__(self, dm, clampName):
        QtGui.QMainWindow.__init__(self)
        self.setWindowTitle(clampName)
        
        self.analysisItems = {
            'inputResistance': 'Ohm', 
            'accessResistance': 'Ohm',
            'capacitance': 'pF',
            'restingPotential': 'V', 
            'restingCurrent': 'A', 
            'fitError': ''
        }
        
        self.params = {
            'mode': 'vc',
            'rate': 40000,
            'cycleTime': .2,
            'recordTime': 0.1,
            'delayTime': 0.03,
            'pulseTime': 0.05,
            'icPulse': -10e-12,
            'vcPulse': -10e-3,
            'icHolding': 0,
            'vcHolding': -50e-3,
            'icHoldingEnabled': False,
            'icPulseEnabled': True,
            'vcHoldingEnabled': False,
            'vcPulseEnabled': True
        }
        
        
        self.paramLock = QtCore.QMutex(QtCore.QMutex.Recursive)

        self.manager = dm
        self.clampName = clampName
        self.thread = PatchThread(self)
        self.cw = QtGui.QWidget()
        self.setCentralWidget(self.cw)
        self.ui = Ui_Form()
        self.ui.setupUi(self.cw)
        
        self.plots = {}
        for k in self.analysisItems:
            p = PlotWidget()
            self.ui.plotLayout.addWidget(p)
            self.plots[k] = p
        
        
        self.stateGroup = WidgetGroup([
            (self.ui.icPulseSpin, 'icPulse', 1e12),
            (self.ui.vcPulseSpin, 'vcPulse', 1e3),
            (self.ui.icHoldSpin, 'icHolding', 1e12),
            (self.ui.vcHoldSpin, 'vcHolding', 1e3),
            (self.ui.icPulseCheck, 'icPulseEnabled'),
            (self.ui.vcPulseCheck, 'vcPulseEnabled'),
            (self.ui.icHoldCheck, 'icHoldingEnabled'),
            (self.ui.vcHoldCheck, 'vcHoldingEnabled'),
            (self.ui.cycleTimeSpin, 'cycleTime', 1),
            (self.ui.pulseTimeSpin, 'pulseTime', 1e3),
            (self.ui.delayTimeSpin, 'delayTime', 1e3),
        ])
        self.stateGroup.setState(self.params)
        
        for p in [self.ui.patchPlot, self.ui.commandPlot]:
            p.setCanvasBackground(QtGui.QColor(0,0,0))
            p.plot()
        self.patchCurve = Qwt.QwtPlotCurve('cell')
        self.patchCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.patchCurve.attach(self.ui.patchPlot)
        self.commandCurve = Qwt.QwtPlotCurve('command')
        self.commandCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.commandCurve.attach(self.ui.commandPlot)
        
        QtCore.QObject.connect(self.ui.startBtn, QtCore.SIGNAL('clicked()'), self.startClicked)
        QtCore.QObject.connect(self.ui.recordBtn, QtCore.SIGNAL('clicked()'), self.recordClicked)
        QtCore.QObject.connect(self.ui.resetBtn, QtCore.SIGNAL('clicked()'), self.resetClicked)
        QtCore.QObject.connect(self.thread, QtCore.SIGNAL('finished()'), self.threadStopped)
        QtCore.QObject.connect(self.thread, QtCore.SIGNAL('newFrame'), self.handleNewFrame)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('clicked()'), self.updateParams)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('clicked()'), self.updateParams)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.updateParams)
                
        ## Configure analysis plots, curves, and data arrays
        self.analysisCurves = {}
        self.analysisData = {'time': []}
        for n in self.analysisItems:
            w = getattr(self.ui, n+'Check')
            QtCore.QObject.connect(w, QtCore.SIGNAL('clicked()'), self.showPlots)
            p = self.plots[n]
            p.setCanvasBackground(QtGui.QColor(0,0,0))
            p.plot()
            for suf in ['', 'Std']:
                self.analysisCurves[n+suf] = Qwt.QwtPlotCurve(n+suf)
                self.analysisCurves[n+suf].setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
                self.analysisCurves[n+suf].attach(p)
                self.analysisData[n+suf] = []
        self.showPlots()
        self.updateParams()
        self.show()
    
    def showPlots(self):
        """Show/hide analysis plot widgets"""
        for n in self.analysisItems:
            w = getattr(self.ui, n+'Check')
            p = self.plots[n]
            if w.isChecked():
                p.show()
            else:
                p.hide()
    
    def updateParams(self, *args):
        l = QtCore.QMutexLocker(self.paramLock)
        if self.ui.icModeRadio.isChecked():
            mode = 'ic'
        else:
            mode = 'vc'
        self.params['mode'] = mode
        state = self.stateGroup.state()
        for p in self.params:
            if p in state:
                self.params[p] = state[p]
        self.params['recordTime'] = self.params['delayTime'] *2.0 + self.params['pulseTime']
        l.unlock()
        self.thread.updateParams()
        
    def recordClicked(self):
        if self.ui.recordBtn.isChecked():
            if len(self.analysisData['time']) > 0:
                data = self.makeAnalysisArray()
                sd = self.storageDir()
                sd.writeFile(data, self.clampName, appendAxis='Time', newFile=True)
                
    def storageDir(self):
        return self.manager.getCurrentDir().getDir('Patch', create=True)
                
    def storageFile(self):
        sd = self.storageDir()
        return sd.getFile(self.clampName, create=True)
            
        
    def resetClicked(self):
        for n in self.analysisData:
            self.analysisData[n] = []
        
    def handleNewFrame(self, frame):
        l = QtCore.QMutexLocker(self.paramLock)
        mode = self.params['mode']
        l.unlock()
        
        data = frame['data'][self.clampName]
        if mode == 'vc':
            scale1 = 1e12
            scale2 = 1e3
        else:
            scale1 = 1e3
            scale2 = 1e12
        self.patchCurve.setData(data.xvals('Time'), data['scaled']*scale1)
        self.commandCurve.setData(data.xvals('Time'), data['raw']*scale2)
        self.ui.patchPlot.plot()
        self.ui.commandPlot.plot()
        
        for k in self.analysisItems:
            if k in frame['analysis']:
                self.analysisData[k].append(frame['analysis'][k])
                
        for r in ['input', 'access']:
            res = r+'Resistance'
            label = getattr(self.ui, res+'Label')
            if frame['analysis'][res] > 1e9:
                label.setText('%0.2f GOhm' % (frame['analysis'][res]*1e-9))
            else:
                label.setText('%0.2f MOhm' % (frame['analysis'][res]*1e-6))
        self.ui.restingPotentialLabel.setText('%0.2f +/- %0.2f mV' % (frame['analysis']['restingPotential']*1e3, frame['analysis']['restingPotentialStd']*1e3))
        self.ui.restingCurrentLabel.setText('%0.2f +/- %0.2f pA' % (frame['analysis']['restingCurrent']*1e9, frame['analysis']['restingCurrentStd']*1e9))
        self.ui.capacitanceLabel.setText('%0.2f pF' % (frame['analysis']['capacitance']*1e12))
        self.ui.fitErrorLabel.setText('%0.2g' % frame['analysis']['fitError'])
        self.analysisData['time'].append(data._info[-1]['startTime'])
        self.updateAnalysisPlots()
        
        ## Record to disk if requested.
        if self.ui.recordBtn.isChecked():
            
            arr = self.makeAnalysisArray(lastOnly=True)
            #print "appending array", arr.shape
            arr.write(self.storageFile().name(), appendAxis='Time')
        
    def makeAnalysisArray(self, lastOnly=False):
        ## Determine how much of the data to include in this array
        if lastOnly:
            sl = slice(-1, None)
        else:
            sl = slice(None)
            
        ## Generate the meta-info structure
        info = [
            {'name': 'Time', 'values': self.analysisData['time'][sl], 'units': 's'},
            {'name': 'Value', 'cols': []}
        ]
        for k in self.analysisItems:
            for s in ['', 'Std']:
                if len(self.analysisData[k+s]) < 1:
                    continue
                info[1]['cols'].append({'name': k+s, 'units': self.analysisItems[k]})
                
        ## Create the blank MetaArray
        data = MetaArray(
            (len(info[0]['values']), len(info[1]['cols'])), 
            dtype=float,
            info=info
        )
        
        ## Fill with data
        for k in self.analysisItems:
            for s in ['', 'Std']:
                if len(self.analysisData[k+s]) < 1:
                    continue
                try:
                    data[:, k+s] = self.analysisData[k+s][sl]
                except:
                    print data.shape, data[:, k+s].shape, len(self.analysisData[k+s][sl])
                    raise
                
        return data
            
            
        
    def updateAnalysisPlots(self):
        for n in self.analysisItems:
            p = self.plots[n]
            if p.isVisible():
                self.analysisCurves[n].setData(self.analysisData['time'], self.analysisData[n])
                if len(self.analysisData[n+'Std']) > 0:
                    self.analysisCurves[p+'Std'].setData(self.analysisData['time'], self.analysisData[n+'Std'])
                p.plot()
    
    def startClicked(self):
        if self.ui.startBtn.isChecked():
            if not self.thread.isRunning():
                self.thread.start()
            self.ui.startBtn.setText('Stop')
        else:
            self.ui.startBtn.setEnabled(False)
            self.thread.stop()
            
    def threadStopped(self):
        self.ui.startBtn.setText('Start')
        self.ui.startBtn.setEnabled(True)
        self.ui.startBtn.setChecked(False)
        
        
class PatchThread(QtCore.QThread):
    def __init__(self, ui):
        self.ui = ui
        self.manager = ui.manager
        self.clampName = ui.clampName
        QtCore.QThread.__init__(self)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.stopThread = True
        self.paramsUpdated = True
                
    def updateParams(self):
        l = QtCore.QMutexLocker(self.lock)
        self.paramsUpdated = True
        
    def run(self):
        try:
            l = QtCore.QMutexLocker(self.lock)
            self.stopThread = False
            clamp = self.manager.getDevice(self.clampName)
            daqName = clamp.config['commandChannel'][0]
            clampName = self.clampName
            self.paramsUpdated = True
            l.unlock()
            
            lastTime = None
            while True:
                lastTime = time.clock()
                
                updateCommand = False
                l.relock()
                if self.paramsUpdated:
                    pl = QtCore.QMutexLocker(self.ui.paramLock)
                    params = self.ui.params.copy()
                    self.paramsUpdated = False
                    pl.unlock()
                    updateCommand = True
                l.unlock()
                
                ## Regenerate command signal if parameters have changed
                numPts = int(float(params['recordTime']) * params['rate'])
                mode = params['mode']
                if params[mode+'HoldingEnabled']:
                    holding = params[mode+'Holding']
                else:
                    holding = 0.
                if params[mode+'PulseEnabled']:
                    amplitude = params[mode+'Pulse']
                else:
                    amplitude = 0.
                cmdData = empty(numPts)
                cmdData[:] = holding
                start = int(params['delayTime'] * params['rate'])
                stop = start + int(params['pulseTime'] * params['rate'])
                cmdData[start:stop] = holding + amplitude
                #cmdData[-1] = holding
                
                cmd = {
                    'protocol': {'duration': params['recordTime'], 'leadTime': 0.02},
                    daqName: {'rate': params['rate'], 'numPts': numPts},
                    clampName: {
                        'mode': params['mode'],
                        'command': cmdData,
                        'holding': holding
                    }
                    
                }
                
                ## Create task
                ## TODO: reuse tasks to improve efficiency
                task = self.manager.createTask(cmd)
                
                ## Execute task
                task.execute()
                
                ## analyze trace 
                result = task.getResult()
                analysis = self.analyze(result[clampName], params)
                frame = {'data': result, 'analysis': analysis}
                
                self.emit(QtCore.SIGNAL('newFrame'), frame)
                
                ## sleep until it is time for the next run
                c = 0
                stop = False
                while True:
                    ## check for stop button every 100ms
                    if c % 1000 == 0:
                        l.relock()
                        if self.stopThread:
                            l.unlock()
                            stop = True
                            break
                        l.unlock()
                    now = time.clock()
                    if now >= (lastTime+params['cycleTime']):
                        break
                    
                    time.sleep(100e-6) ## Wake up every 100us
                    c += 1
                if stop:
                    break
        except:
            print "Error in patch acquisition thread, exiting."
            traceback.print_exception(*sys.exc_info())
        #self.emit(QtCore.SIGNAL('threadStopped'))
            
    def analyze(self, data, params):
        #print "\n\nAnalysis parameters:", params
        ## Extract specific time segments
        base = data['Time': 0.0:params['delayTime']]
        pulse = data['Time': params['delayTime']:params['delayTime']+params['pulseTime']]
        pulseEnd = data['Time': params['delayTime']+(params['pulseTime']*2./3.):params['delayTime']+params['pulseTime']]
        end = data['Time':params['delayTime']+params['pulseTime']:]
        #print "time ranges:", pulse.xvals('Time').min(),pulse.xvals('Time').max(),end.xvals('Time').min(),end.xvals('Time').max()
        ## Exponential fit
        #  v[0] is offset to start of exp
        #  v[1] is amplitude of exp
        #  v[2] is tau
        def expFn(v, t):
            return (v[0]-v[1]) + v[1] * exp(-t / v[2])
        # predictions
        ar = 10e6
        ir = 200e6
        if params['mode'] == 'vc':
            ari = params['vcPulse'] / ar
            iri = params['vcPulse'] / ir
            pred1 = [ari, ari-iri, 1e-3]
            pred2 = [iri-ari, iri-ari, 1e-3]
        else:
            clamp = self.manager.getDevice(self.clampName)
            bridge = float(clamp.getParam('BridgeBalResist', cache=False))
            bridgeOn = clamp.getParam('BridgeBalEnable', cache=False)
            #print "bridge on: '%s'" % bridgeOn, type(bridgeOn)
            if bridgeOn != 'True':
                bridge = 0.0
            #print "Bridge:", bridge, bridgeOn, type(bridgeOn)
            arv = params['icPulse'] * (ar-bridge)
            irv = params['icPulse'] * ir
            pred1 = [arv, -irv, 10e-3]
            pred2 = [irv, irv, 50e-3]
            
        # Fit exponential to pulse and post-pulse traces
        fit1 = scipy.optimize.leastsq(
            lambda v, t, y: y - expFn(v, t), pred1, 
            args=(pulse.xvals('Time')-pulse.xvals('Time').min(), pulse['scaled'] - base['scaled'].mean()),
            maxfev=200, full_output=1, warning=False)
        fit2 = scipy.optimize.leastsq(
            lambda v, t, y: y - expFn(v, t), pred2, 
            args=(end.xvals('Time')-end.xvals('Time').min(), end['scaled'] - base['scaled'].mean()),
            maxfev=200, full_output=1, warning=False)
            
        
        err = max(abs(fit1[2]['fvec']).sum(), abs(fit2[2]['fvec']).sum())
        #err = max(fit1[2]['nfev'], fit2[2]['nfev'])
        
        #times = pulse.xvals('Time')-pulse.xvals('Time').min()
        #err = fromfunction(lambda t: pulse['scaled'][t] - expFn(fit1[0], times[t]), pulse['scaled'].shape)
        #err *= err
        #err = err.sum()
        
        
        # Average fit1 with fit2 (needs massaging since fits have different starting points)
        #print fit1
        fit1 = fit1[0]
        fit2 = fit2[0]
        fitAvg = [
            0.5 * (fit1[0] - (fit2[0] - (fit1[0] - fit1[1]))),
            0.5 * (fit1[1] - fit2[1]),
            0.5 * (fit1[2] + fit2[2])            
        ]
        fitAvg = fit1
        
        0.5 * (fit1[0] + (fit2[0] * array([-1, -1, 1])))
        #print pred1, fit1, pred2, fit2, fitAvg
        
        ## Handle anelysis differently depenting on clamp mode
        if params['mode'] == 'vc':
            iBase = base['Channel': 'scaled']
            iPulse = pulseEnd['Channel': 'scaled'] 
            vBase = base['Channel': 'Command']
            vPulse = pulse['Channel': 'Command'] 
            
            vStep = vPulse.mean() - vBase.mean()
            aRes = vStep / fitAvg[0]
            iRes = vStep / (fitAvg[0] - fitAvg[1])
            cap = fitAvg[2] / aRes
        if params['mode'] == 'ic':
            iBase = base['Channel': 'Command']
            iPulse = pulse['Channel': 'Command'] 
            vBase = base['Channel': 'scaled']
            vPulse = pulseEnd['Channel': 'scaled'] 
            
            iStep = iPulse.mean() - iBase.mean()
            #print "current step:", iStep
            #print "bridge:", bridge
            aRes = (fitAvg[0] / iStep) + bridge
            iRes = (-fitAvg[1] / iStep) + bridge
            cap = fitAvg[2] / (iRes-aRes)
            
            
            
        rmp = vBase.mean()
        rmps = vBase.std()
        rmc = iBase.mean()
        rmcs = iBase.std()
        
            
        return {
            'inputResistance': iRes, 
            'accessResistance': aRes,
            'capacitance': cap,
            'restingPotential': rmp, 'restingPotentialStd': rmps,
            'restingCurrent': rmc, 'restingCurrentStd': rmcs,
            'fitError': err
        }
            
    def stop(self, block=False):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()
        if block:
            self.wait()