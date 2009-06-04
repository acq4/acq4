# -*- coding: utf-8 -*-
from PatchTemplate import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
import traceback, sys, time
from numpy import *

class PatchWindow(QtGui.QMainWindow):
    def __init__(self, dm, clampName):
        QtGui.QMainWindow.__init__(self)
        self.setWindowTitle(clampName)
        self.params = {
            'mode': 'vc',
            'rate': 40000,
            'cycleTime': .2,
            'recordTime': 0.05,
            'delayTime': 0.01,
            'pulseTime': 0.02,
            'icPulse': 10e-12,
            'vcPulse': 10e-3,
            'icHolding': 0,
            'vcHolding': -50e-3,
            'icHoldingEnabled': False,
            'icPulseEnabled': True,
            'vcHoldingEnabled': False,
            'vcPulseEnabled': True
        }
        
        self.stateGroup = WidgetGroup([
            (self.ui.icPulseSpin, 'icPulse', 1e12),
            (self.ui.vcPulseSpin, 'vcPulse', 1e3),
            (self.ui.icHoldSpin, 'icHolding', 1e12),
            (self.ui.vcHoldSpin, 'vcHolding', 1e3),
            (self.ui.icPulseCheck, 'icPulseEnabled'),
            (self.ui.vcPulseCheck, 'vcPulseEnabled'),
            (self.ui.icHoldCheck, 'icHoldingEnabled'),
            (self.ui.vcHoldCheck, 'vcHoldingEnabled'),
            (self.ui.cycleTimeSpin, 'cycleTime', 1e3),
        ])
        self.stateGroup.restoreState(self.params)
        
        self.paramLock = QtCore.QMutex(QtCore.QMutex.Recursive)

        self.dm = dm
        self.clampName = clampName
        self.thread = PatchThread(self)
        self.cw = QtGui.QWidget()
        self.setCentralWidget(self.cw)
        self.ui = Ui_Form()
        self.ui.setupUi(self.cw)
        
        #self.ui.icPulseSpin.setValue(self.params['icPulse']*1e12)
        #self.ui.vcPulseSpin.setValue(self.params['vcPulse']*1e3)
        #self.ui.icHoldSpin.setValue(self.params['icHolding']*1e12)
        #self.ui.vcHoldSpin.setValue(self.params['vcHolding']*1e3)
        #self.ui.icPulseCheck.setChecked(self.params['icPulseEnabled'])
        #self.ui.vcPulseCheck.setChecked(self.params['vcPulseEnabled'])
        #self.ui.icHoldCheck.setChecked(self.params['icHoldingEnabled'])
        #self.ui.vcHoldCheck.setChecked(self.params['vcHoldingEnabled'])
        #self.ui.cycleTimeSpin.setValue(self.params['cycleTime']*1e3)
        
        
        for p in [self.ui.patchPlot, self.ui.commandPlot, self.ui.analysisPlot]:
            p.setCanvasBackground(QtGui.QColor(0,0,0))
            p.replot()
        self.patchCurve = Qwt.QwtPlotCurve('cell')
        self.patchCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.patchCurve.attach(self.ui.patchPlot)
        self.commandCurve = Qwt.QwtPlotCurve('command')
        self.commandCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.commandCurve.attach(self.ui.commandPlot)
        self.analysisCurve = Qwt.QwtPlotCurve('analysis')
        self.analysisCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.analysisCurve.attach(self.ui.analysisPlot)
        self.analysisData = {'mr': [], 'rmp': [], 'tau': [], 'time': []}
        
        QtCore.QObject.connect(self.ui.startBtn, QtCore.SIGNAL('clicked()'), self.startClicked)
        QtCore.QObject.connect(self.thread, QtCore.SIGNAL('finished()'), self.threadStopped)
        QtCore.QObject.connect(self.thread, QtCore.SIGNAL('newFrame(PyQt_PyObject)'), self.handleNewFrame)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('clicked()'), self.updateParams)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('clicked()'), self.updateParams)
        #QtCore.QObject.connect(self.ui.icPulseSpin, QtCore.SIGNAL('valueChanged(double)'), self.updateParams)
        #QtCore.QObject.connect(self.ui.icHoldSpin, QtCore.SIGNAL('valueChanged(double)'), self.updateParams)
        #QtCore.QObject.connect(self.ui.icPulseCheck, QtCore.SIGNAL('clicked()'), self.updateParams)
        #QtCore.QObject.connect(self.ui.icHoldCheck, QtCore.SIGNAL('clicked()'), self.updateParams)
        #QtCore.QObject.connect(self.ui.vcPulseSpin, QtCore.SIGNAL('valueChanged(double)'), self.updateParams)
        #QtCore.QObject.connect(self.ui.vcHoldSpin, QtCore.SIGNAL('valueChanged(double)'), self.updateParams)
        #QtCore.QObject.connect(self.ui.vcPulseCheck, QtCore.SIGNAL('clicked()'), self.updateParams)
        #QtCore.QObject.connect(self.ui.vcHoldCheck, QtCore.SIGNAL('clicked()'), self.updateParams)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.updateParams)
                
        self.show()
        
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
        #self.params['icHoldingEnabled'] = self.ui.icHoldCheck.isChecked()
        #self.params['icPulseEnabled'] = self.ui.icPulseCheck.isChecked()
        #self.params['icHolding'] = self.ui.icHoldSpin.value() * 1e-12
        #self.params['icPulse'] = self.ui.icPulseSpin.value() * 1e-12
        #self.params['vcHoldingEnabled'] = self.ui.vcHoldCheck.isChecked()
        #self.params['vcPulseEnabled'] = self.ui.vcPulseCheck.isChecked()
        #self.params['vcHolding'] = self.ui.vcHoldSpin.value() * 1e-3
        #self.params['vcPulse'] = self.ui.vcPulseSpin.value() * 1e-3
        l.unlock()
        self.thread.updateParams()
        
    #def setParameter(self, param, value):
        #if param in ['cycleTime', 'recordTime', 'delayTime', 'pulseTime']:
            ##w = getattr(self.ui, param+'Spin')
            #l = QtCore.QMutexLocker(self.paramLock)
            #self.params[param] = value
            #l.unlock()
        #self.thread.updateParams()
        
        
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
        self.ui.patchPlot.replot()
        self.ui.commandPlot.replot()
        
        for k in ['mr', 'rmp', 'tau']:
            self.analysisData[k].append(frame['analysis'][k])
        self.analysisData['time'].append(data._info[-1]['startTime'])
        self.updateAnalysisPlot()
        
    def updateAnalysisPlot(self):
        if self.ui.inputResistanceRadio.isChecked():
            p = 'mr'
        elif self.ui.restingPotentialRadio.isChecked():
            p = 'rmp'
        elif self.ui.timeConstantRadio.isChecked():
            p = 'tau'
        self.analysisCurve.setData(self.analysisData['time'], self.analysisData[p])
        self.ui.analysisPlot.replot()
    
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
        self.dm = ui.dm
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
            clamp = self.dm.getDevice(self.clampName)
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
                
                cmd = {
                    'protocol': {'duration': params['recordTime']},
                    daqName: {'rate': params['rate'], 'numPts': numPts},
                    clampName: {
                        'mode': params['mode'],
                        'command': cmdData
                    }
                    
                }
                
                ## Create task
                ## TODO: reuse tasks to improve efficiency
                task = self.dm.createTask(cmd)
                
                ## Execute task
                task.execute()
                
                ## measure resistance, RMP, and tau 
                res = task.getResult()
                (mr, rmp, tau) = self.analyze(res[clampName], params)
                frame = {'data': res, 'analysis': {'mr': mr, 'rmp': rmp, 'tau': tau}}
                
                self.emit(QtCore.SIGNAL('newFrame(PyQt_PyObject)'), frame)
                
                ## sleep until it is time for the next run
                while True:
                    now = time.clock()
                    if now >= (lastTime+params['cycleTime']):
                        break
                    time.sleep(100e-6)
                l.relock()
                if self.stopThread:
                    l.unlock()
                    break
                l.unlock()
        except:
            print "Error in patch acquisition thread, exiting."
            traceback.print_exception(*sys.exc_info())
        #self.emit(QtCore.SIGNAL('threadStopped'))
            
    def analyze(self, data, params):
        base = data['Time': 0.0:params['delayTime']]
        pulse = data['Time': params['delayTime']:params['delayTime']+params['pulseTime']]
        pulseEnd = data['Time': params['delayTime']+(params['pulseTime']*2./3.):params['delayTime']+params['pulseTime']]
        
        if params['mode'] == 'vc':
            iBase = base['Channel': 'scaled'].mean()
            iPulse = pulseEnd['Channel': 'scaled'].mean() 
            vBase = base['Channel': 'raw'].mean()
            vPulse = pulse['Channel': 'raw'].mean() 
            ir = (vPulse-vBase) / (iPulse-iBase)
            rmp = vBase.mean()
        if params['mode'] == 'ic':
            iBase = base['Channel': 'raw'].mean()
            iPulse = pulse['Channel': 'raw'].mean() 
            vBase = base['Channel': 'scaled'].mean()
            vPulse = pulseEnd['Channel': 'scaled'].mean() 
            rmp = vBase.mean()
            ir = (vPulse-vBase) / (iPulse-iBase)
            # exponential fit starting point: y = est[0] + est[1] * exp(-x*est[2])
            #estimate = [rmp
            ## Exponential fit
            #fit = leastsq(lambda v, x, y: y - (v[0] - v[1]*exp(-x * v[2])), [10, 2, 3], args=(array(x), array(y)))
            
        return (ir,rmp,0)
            
    def stop(self, block=False):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()
        if block:
            self.wait()