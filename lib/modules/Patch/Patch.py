# -*- coding: utf-8 -*-
from PatchTemplate import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt


class PatchWindow(QtGui.QMainWindow):
    def __init__(self, dm, clampName):
        QtGui.QMainWindow.__init__(self)
        self.dm = dm
        self.clampName = clampName
        self.thread = PatchThread(self)
        self.cw = QtGui.QWidget()
        self.setCentralWidget(self.cw)
        self.ui = Ui_Form()
        self.ui.setupUi(self.cw)
        
        self.ui.patchPlot.setCanvasBackground(QtGui.QColor(0,0,0))
        self.ui.patchPlot.replot()
        self.patchCurve = Qwt.QwtPlotCurve('cell')
        self.patchCurve.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        self.patchCurve.attach(self.patchPlot)
        
        self.show()
        
    def handleNewFrame(self, frame):
        self.patchCurve.setData(frame['data']['primary'], frame['data'].xvals('Time'))
        self.ui.patchPlot.replot()
        pass
        
class PatchThread(QtCore.QThread):
    def __init__(self, ui):
        self.ui = ui
        self.dm = ui.dm
        self.clampName = ui.clampName
        QtCore.QThread.__init__(self)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.stopThread = True
        self.params = {
            'mode': 'vc',
            'rate': 40000,
            'cycleTime': 0.25,
            'recordTime': 0.2,
            'delayTime': 0.01,
            'pulseTime': 0.1,
            'icPulseAmplitude': 10e-12,
            'vcPulseAmplitude': 10e-3
            'icHolding': 0,
            'vcHolding': 0
        }
        
    def setParam(self, param, value):
        l = QtCore.QMutexLocker(self.lock)
        ## If param or value are complex objects, make sure they are copied here rather than assigning them in!
        self.params[param] = value
        l.unlock()
        self.emit(QtCore.SIGNAL('paramChanged'), (param, value))
        
        
    def run(self):
        self.lock.lock()
        self.stopThread = False
        daqName = self.dm.config[clampName]['commandChannel'][0]
        clampName = self.clampName
        
        self.lock.unlock()
        
        lastTime = None
        while true:
            lastTime = time.clock()
            
            l = self.QMutexLocker(self.lock)
            params = self.params.copy()
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
            frame = {'data': res}
            
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
        