from PyQt4 import QtGui
from pyqtgraph.PlotWidget import PlotWidget

class LaserProtoGui(QtGui.QWidget):
    def __init__(self, dev, prot):
        DAQGenericProtoGui.init(self, dev, prot, ownUi=False)
        
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.splitter1 = QtGui.QSplitter()
        self.splitter1.setOrientation(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)
        
        self.ctrlSplitter = QtGui.QSplitter()
        self.ctrlSplitter.setOrientation(QtCore.Qt.Vertical)
        self.plotSplitter = QtGui.QSplitter()
        self.plotSplitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter1.addWidget(self.ctrlSplitter)
        self.splitter1.addWidget(self.plotSplitter)
        
        ## do stuff, then:
        self.powerWidget, self.powerPlot = self.createChannelWidget('power')
        self.ctrlSplitter.addWidget(self.powerWidget)
        self.plotSplitter.addWidget(self.powerPlot)
        
        if self.dev.hasTriggerableShutter:
            #(self.shutterWidget, self.shutterPlot) = self.createChannelWidget('shutter')
            self.shutterPlot = PlotWidget()
            self.plotSplitter.addWidget(self.shutterPlot)
            self.shutterPlot.hide()
        if self.dev.hasQSwitch:
            #self.qSwitchWidget, self.qSwitchPlot = self.createChannelWidget('qSwitch')
            self.qSwitchPlot = PlotWidget()
            self.plotSplitter.addWidget(self.qSwitchPlot)
            self.qSwitchPlot.hide()
        if self.dev.hasPCell:
            #self.pCellWidget, self.pCellPlot = self.createChannelWidget('pCell')
            self.pCellPlot = PlotWidget()
            self.plotSplitter.addWidget(self.pCellPlot)
            self.pCellPlot.hide()
            
            
        ## catch self.powerWidget.sigDataChanged and connect it to functions that calculate and plot raw shutter and qswitch traces
        self.powerWidget.sigDataChanged.connect(self.powerCmdChanged)
        
    def saveState(self):
        pass
        ## basically identical to Axopatch
        
    def restoreState(self, state):
        pass
    
    def generateProtocol(self, params=None):
        pass
    
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
      
        