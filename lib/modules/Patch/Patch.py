# -*- coding: utf-8 -*-
from PatchTemplate import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
import traceback, sys

class PatchWindow(QtGui.QMainWindow):
    def __init__(self, dm, clampName):
        QtGui.QMainWindow.__init__(self)

        self.params = {
            'mode': 'vc',
            'rate': 40000,
            'cycleTime': 0.25,
            'recordTime': 0.05,
            'delayTime': 0.01,
            'pulseTime': 0.02,
            'icPulseAmplitude': 10e-12,
            'vcPulseAmplitude': 10e-3,
            'icHolding': 0,
            'vcHolding': 0
        }
        self.paramLock = QtCore.QMutex(QtCore.QMutex.Recursive)

        self.dm = dm
        self.clampName = clampName
        self.thread = PatchThread(self)
        self.cw = QtGui.QWidget()
        self.setCentralWidget(self.cw)
        self.ui = Ui_Form()
        self.ui.setupUi(self.cw)
        
        for p in [self.ui.patchPlot, self.ui.commandPlot, self.ui.analysisPlot]:
            p.setCanvasBackground(QtGui.QColor(0,0,0))
            p.replot()
        self.patchCurve = Qwt.QwtPlotCurve('cell')
        self.patchCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.patchCurve.attach(self.ui.patchPlot)
        self.commandCurve = Qwt.QwtPlotCurve('command')
        self.commandCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.commandCurve.attach(self.ui.patchPlot)
        self.analysisCurve = Qwt.QwtPlotCurve('analysis')
        self.analysisCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.analysisCurve.attach(self.ui.patchPlot)
        self.analysisData = {'mr': [], 'rmp': [], 'tau': [], 'time': []}
        
        QtCore.QObject.connect(self.ui.startBtn, QtCore.SIGNAL('clicked()'), self.startClicked)
        QtCore.QObject.connect(self.thread, QtCore.SIGNAL('finished()'), self.threadStopped)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('toggled()'), self.updateMode)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('toggled()'), self.updateMode)
        QtCore.QObject.connect(self.ui.cycleTimeSpin, QtCore.SIGNAL('changed(double)'), lambda x: self.setParameter('cycleTime', x))
        QtCore.QObject.connect(self.ui.recordTimeSpin, QtCore.SIGNAL('changed(double)'), lambda x: self.setParameter('recordTime', x))
        QtCore.QObject.connect(self.ui.delayTimeSpin, QtCore.SIGNAL('changed(double)'), lambda x: self.setParameter('delayTime', x))
        QtCore.QObject.connect(self.ui.pulseTimeSpin, QtCore.SIGNAL('changed(double)'), lambda x: self.setParameter('pulseTime', x))
        
        self.show()
        
        
    def updateMode(self):
        l = QtCore.QMutexLocker(self.paramLock)
        
        if self.ui.icModeRadio.isChecked():
            self.params['mode'] = 'ic'
            self.ui.pulseSpin.setValue(self.params['icPulseAmplitude'])
            self.ui.holdSpin.setValue(self.params['icHolding'])
        else:
            self.params['mode'] = 'vc'
            self.ui.pulseSpin.setValue(self.params['vcPulseAmplitude'])
            self.ui.holdSpin.setValue(self.params['vcHolding'])
            
        l.unlock()
        self.thread.paramsUpdated()
        
    def setParameter(self, param, value):
        if param in ['cycleTime', 'recordTime', 'delayTime', 'pulseTime']:
            #w = getattr(self.ui, param+'Spin')
            l = QtCore.QMutexLocker(self.paramLock)
            self.params[param] = value
            l.unlock()
        self.thread.paramsUpdated()
        
        
    def handleNewFrame(self, frame):
        self.patchCurve.setData(frame['data']['scaled'], frame['data'].xvals('Time'))
        self.commandCurve.setData(frame['data']['raw'], frame['data'].xvals('Time'))
        self.ui.patchPlot.replot()
        self.ui.commandPlot.replot()
        
        for k in ['mr', 'rmp', 'tau']:
            self.analysisData[k].append(frame['analysis'][k])
        self.analysisData['time'].append(frame['data']._info[-1]['startTime'])
        self.updateAnalysisPlot()
        
    def updateAnalysisPlot(self):
        if self.ui.membraneResistanceRadio.isChecked():
            p = 'mr'
        elif self.ui.restingMembranePotentialRadio.isChecked():
            p = 'rmp'
        elif self.ui.timeConstantRadio.isChecked():
            p = 'tau'
        self.analysisCurve.setData(self.analysisData[p], self.analysisData['time'])
        self.analysisPlot.replot()
    
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
    def __init__(self, ui, params):
        self.ui = ui
        self.dm = ui.dm
        self.clampName = ui.clampName
        QtCore.QThread.__init__(self)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.stopThread = True
        
        ## Note that params is the same dict as held by the GUI thread, so accessing it is NOT thread safe.
        self.params = params
        
        self.paramsUpdated = True
                
    def paramsUpdated(self):
        l = QtCore.QMutexLocker(self.lock)
        self.paramsUpdated = True
        
    def run(self):
        try:
            l = QtCore.QMutexLocker(self.lock)
            self.stopThread = False
            clamp = self.dm.getDevice(self.clampName)
            daqName = clamp.config['commandChannel'][0]
            clampName = self.clampName
            
            l.unlock()
            
            lastTime = None
            while true:
                lastTime = time.clock()
                
                updateCommand = False
                l.lock()
                if self.paramsUpdated:
                    pl = QtCore.QMutexLocker(self.ui.paramsLock)
                    params = self.params.copy()
                    pl.unlock()
                    updateCommand = True
                l.unlock()
                
                ## Regenerate command signal if parameters have changed
                numPts = int(float(params['recordTime']) * params['rate'])
                mode = params['mode']
                holding = params[mode+'Holding']
                amplitude = params[mode+'PulseAmplitude']
                cmdData = empty(numPts)
                cmdData[:] = holding
                start = int(params['delayTime'] * params['rate'])
                stop = start + int(params['pulseTime'] * params['rate'])
                cmdData[start:stop] = amplitude
                
                cmd = {
                    'protocol': {'time': params['recordTime']},
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
                (mr, rmp, tau) = self.analyze(res, params)
                frame = {'data': res, 'analysis': {'mr': mr, 'rmp': rmp, 'tau': tau}}
                
                self.emit(QtCore.SIGNAL('newFrame'), frame)
                
                ## sleep until it is time for the next run
                while True:
                    now = time.clock()
                    if now < (lastTime+params['cycleTime']):
                        break
                    time.sleep(100e-6)
                l.lock()
                if self.stopThread:
                    l.unlock()
                    break
                l.unlock()
        except:
            print "Error in patch acquisition thread, exiting."
            traceback.print_exception(*sys.exc_info())
        #self.emit(QtCore.SIGNAL('threadStopped'))
            
    def analyze(self, data, params):
        
        
        
        return (0,0,0)
            
    def stop(self, block=False):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()
        if block:
            self.wait()