from PyQt4 import QtGui, QtCore
from pyqtgraph.PlotWidget import PlotWidget
from lib.devices.DAQGeneric import DAQGenericProtoGui
from SequenceRunner import runSequence
from pyqtgraph.functions import siFormat
#from FeedbackButton import FeedbackButton

class LaserProtoGui(DAQGenericProtoGui):
    def __init__(self, dev, prot):
        DAQGenericProtoGui.__init__(self, dev, prot, ownUi=False)
        
        self.cache = {}
        
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.splitter1 = QtGui.QSplitter()
        self.splitter1.setOrientation(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)
        
        self.ctrlLayout = QtGui.QVBoxLayout()
        wid1 = QtGui.QWidget()
        wid1.setLayout(self.ctrlLayout)
        self.plotSplitter = QtGui.QSplitter()
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter1.addWidget(wid1)
        self.splitter1.addWidget(self.plotSplitter)
        #wid = QtGui.QWidget()
        hLayout = QtGui.QHBoxLayout()
        #wid.setLayout(hLayout)
        self.ctrlLayout.addLayout(hLayout)

        label = QtGui.QLabel("Current Power at Sample: ")
        self.powerLabel = QtGui.QLabel("")
        self.powerLabel.font().setBold(True)
        self.powerLabel.font().setPointSize(12)
        self.checkPowerBtn = QtGui.QPushButton("Check Power")
        if not self.dev.hasPowerIndicator:
            self.checkPowerBtn.setEnabled(False)
        hLayout.addWidget(label)
        hLayout.addWidget(self.powerLabel)
        hLayout.addWidget(self.checkPowerBtn)
        
        
        self.powerWidget, self.powerPlot = self.createChannelWidget('power', daqName=self.dev.getDAQName()[0])
        self.ctrlLayout.addWidget(self.powerWidget)
        self.plotSplitter.addWidget(self.powerPlot)
        self.powerWidget.setMeta('y', units='W', siPrefix=True, dec=True, step=0.5, minStep=1e-3, limits=(0, None))
        self.powerWidget.setMeta('xy', units='J', siPrefix=True, dec=True, step=0.5, minStep=1e-6, limits=(0, None))
        self.powerWidget.setMeta('x', units='s', siPrefix=True, dec=True, step=0.5, minStep=1e-6, limits=(None, None))
        
        if self.dev.hasTriggerableShutter:
            #(self.shutterWidget, self.shutterPlot) = self.createChannelWidget('shutter')
            self.shutterPlot = PlotWidget(name='%s.shutter'%self.dev.name)
            self.shutterPlot.setLabel('left', text='Shutter')
            self.plotSplitter.addWidget(self.shutterPlot)
            #self.shutterPlot.hide()
        if self.dev.hasQSwitch:
            #self.qSwitchWidget, self.qSwitchPlot = self.createChannelWidget('qSwitch')
            self.qSwitchPlot = PlotWidget(name='%s.qSwitch'%self.dev.name)
            self.qSwitchPlot.setLabel('left', text='Q-Switch')
            self.plotSplitter.addWidget(self.qSwitchPlot)
            #self.qSwitchPlot.hide()
        if self.dev.hasPCell:
            #self.pCellWidget, self.pCellPlot = self.createChannelWidget('pCell')
            self.pCellPlot = PlotWidget(name='%s.pCell'%self.dev.name)
            self.pCellPlot.setLabel('left', text='Pockel Cell', units='V')
            self.plotSplitter.addWidget(self.pCellPlot)
            #self.pCellPlot.hide()
            
            
        ## catch self.powerWidget.sigDataChanged and connect it to functions that calculate and plot raw shutter and qswitch traces
        self.powerWidget.sigDataChanged.connect(self.powerCmdChanged)
        self.checkPowerBtn.clicked.connect(self.dev.outputPower)
        self.dev.sigPowerChanged.connect(self.updatePowerLabel)
        
        self.dev.outputPower()
        
        
    def updatePowerLabel(self, power):
        if power is None:
            return
        self.powerLabel.setText(str(siFormat(power*self.dev.params['scopeTransmission'], suffix='W')))
    
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = {}
        state['daqState'] = DAQGenericProtoGui.saveState(self)
        return state
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        return DAQGenericProtoGui.restoreState(self, state['daqState'])
    
    def describe(self, params=None):
        state = self.saveState()
        ps = state['daqState']['channels']['power']
        desc = {'mode': 'power', 'command': ps['waveGeneratorWidget']}
        return desc
    
    def generateProtocol(self, params=None):
        """Return a cmd dictionary suitable for passing to LaserTask."""
        ## Params looks like: {'amp': 7} where 'amp' is the name of a sequence parameter, and 7 is the 7th value in the list of 'amp'
        rate = self.powerWidget.rate
        wave = self.powerWidget.getSingleWave(params)
        rawCmds = self.cache.get(id(wave), self.dev.getChannelCmds({'powerWaveform':wave}, rate)) ## returns {'shutter': array(...), 'qSwitch':array(..), 'pCell':array(...)}
        
        ### structure protocol in DAQGeneric-compatible way
        cmd = {}
        for k in rawCmds:
            cmd[k] = {}
            cmd[k]['command'] = rawCmds[k]
            
        cmd['powerWaveform'] = wave  ## just to allow the device task to store this data
        cmd['ignorePowerWaveform'] = True
        return  cmd
    
    def powerCmdChanged(self):
        self.clearRawPlots()
        self.cache = {}
        rate = self.powerWidget.rate
        
        #### calculate, cache and display sequence waves for shutter/qSwitch/pCell
        params = {}
        ps = self.powerWidget.listSequence()
        for k in ps:
            params[k] = range(len(ps[k]))
        ## get power waveforms
        waves = []
        runSequence(lambda p: waves.append(self.powerWidget.getSingleWave(p)), params, params.keys()) ## appends waveforms for the entire parameter space to waves
        
        for w in waves:
            if w is not None:
                ## need to translate w into raw traces, plot them, and cache them (using id(w) as a key)
                rawWaves = self.dev.getChannelCmds({'powerWaveform':w}, rate) ## calculate raw waveforms for shutter/qSwitch/pCell from powerWaveform
                self.cache[id(w)] = rawWaves ## cache the calculated waveforms
                self.plotRawCurves(rawWaves, color=QtGui.QColor(100, 100, 100)) ## plot the raw waveform in it's appropriate plot in grey
        
        ## calculate (or pull from cache) and display single-mode wave in red
        single = self.powerWidget.getSingleWave()
        if single is not None:
            rawSingle = self.cache.get(id(single), self.dev.getChannelCmds({'powerWaveform':single}, rate))
            self.plotRawCurves(rawSingle, color=QtGui.QColor(200, 100, 100))
    
                      
    def plotRawCurves(self, data, color=QtGui.QColor(100, 100, 100)):
        if 'shutter' in data:
            self.shutterPlot.plot(y=data['shutter'], x=self.powerWidget.timeVals, pen=QtGui.QPen(color))
        if 'qSwitch' in data:
            self.qSwitchPlot.plot(y=data['qSwitch'], x=self.powerWidget.timeVals, pen=QtGui.QPen(color))
        if 'pCell' in data:
            self.pCellPlot.plot(y=data['pCell'], x=self.powerWidget.timeVals, pen=QtGui.QPen(color))
      
    def clearRawPlots(self):
        for p in ['shutterPlot', 'qSwitchPlot', 'pCellPlot']:
            if hasattr(self, p):
                getattr(self, p).clear()