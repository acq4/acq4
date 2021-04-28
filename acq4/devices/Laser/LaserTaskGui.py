from __future__ import print_function
from acq4.util import Qt
from pyqtgraph import PlotWidget, mkPen
from acq4.devices.DAQGeneric import DAQGenericTaskGui
from acq4.util.SequenceRunner import runSequence
from pyqtgraph.functions import siFormat
from acq4.util.HelpfulException import HelpfulException
from six.moves import range

Ui_Form = Qt.importTemplate('.taskTemplate')


class LaserTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner):
        DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)
        
        self.ui = Ui_Form()
        
        self.cache = {}
        
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.splitter1 = Qt.QSplitter()
        self.splitter1.setOrientation(Qt.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)
        
        self.ctrlLayout = Qt.QVBoxLayout()
        wid1 = Qt.QWidget()
        wid1.setLayout(self.ctrlLayout)
        self.plotSplitter = Qt.QSplitter()
        self.plotSplitter.setOrientation(Qt.Qt.Vertical)
        self.splitter1.addWidget(wid1)
        self.splitter1.addWidget(self.plotSplitter)
        wid2 = Qt.QWidget()
        self.ui.setupUi(wid2)
        self.ctrlLayout.addWidget(wid2)

        if not self.dev.hasPowerIndicator:
            self.ui.checkPowerBtn.setEnabled(False)
            self.ui.checkPowerCheck.hide()
            self.ui.checkPowerCheck.setChecked(False)
        if not self.dev.hasTunableWavelength:
            self.ui.wavelengthWidget.hide()
        
        
        self.powerWidget, self.powerPlot = self.createChannelWidget('power', daqName=self.dev.getDAQName()[0])
        
        ## all we want is the function generator
        self.powerFnGenerator = self.powerWidget.ui.waveGeneratorWidget
        self.powerWidget.hide()
        self.ctrlLayout.addWidget(self.powerFnGenerator)
        self.powerFnGenerator.show()
        
        self.plotSplitter.addWidget(self.powerPlot)
        self.powerWidget.setMeta('y', units='W', siPrefix=True, dec=True, step=0.5, minStep=1e-3, limits=(0, None))
        self.powerWidget.setMeta('xy', units='J', siPrefix=True, dec=True, step=0.5, minStep=1e-6, limits=(0, None))
        self.powerWidget.setMeta('x', units='s', siPrefix=True, dec=True, step=0.5, minStep=1e-6, limits=(None, None))
        
        if self.dev.hasTriggerableShutter:
            self.shutterPlot = PlotWidget(name='%s.shutter'%self.dev.name)
            self.shutterPlot.setLabel('left', text='Shutter')
            self.plotSplitter.addWidget(self.shutterPlot)
        if self.dev.hasQSwitch:
            self.qSwitchPlot = PlotWidget(name='%s.qSwitch'%self.dev.name)
            self.qSwitchPlot.setLabel('left', text='Q-Switch')
            self.plotSplitter.addWidget(self.qSwitchPlot)
        if self.dev.hasPCell:
            self.pCellPlot = PlotWidget(name='%s.pCell'%self.dev.name)
            self.pCellPlot.setLabel('left', text='Pockel Cell', units='V')
            self.plotSplitter.addWidget(self.pCellPlot)
            
        ## catch self.powerWidget.sigDataChanged and connect it to functions that calculate and plot raw shutter and qswitch traces
        self.powerWidget.sigDataChanged.connect(self.powerCmdChanged)
        self.ui.checkPowerBtn.clicked.connect(self._handleCheckPowerBtnClick)
        self.dev.sigOutputPowerChanged.connect(self.laserPowerChanged)
        self.dev.sigSamplePowerChanged.connect(self.samplePowerChanged)
        
        
        self.dev.outputPower()
        
    def laserPowerChanged(self, power, valid):
        
        ## update label
        if power is None:
            self.ui.outputPowerLabel.setText("?")
        else:
            self.ui.outputPowerLabel.setText(siFormat(power, suffix='W'))
            
        if not valid:
            self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #B00}")
        else:
            self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #000}")

    def _handleCheckPowerBtnClick(self):
        self.dev.outputPower(forceUpdate=True)

    def samplePowerChanged(self, power):
        if power is None:
            self.ui.samplePowerLabel.setText("?")
            return
        else:
            self.ui.samplePowerLabel.setText(siFormat(power, suffix='W'))

        if self.dev.hasPCell:
            raise Exception('stub')
        else:
            ## adjust length of pulse to correct for new power
            if self.ui.adjustLengthCheck.isChecked():
                en = {}
                for param in self.powerWidget.ui.waveGeneratorWidget.stimParams:
                    en[param.name()] = param['sum']
                self.powerWidget.setMeta('y', value=power, readonly=True)
                for param in self.powerWidget.ui.waveGeneratorWidget.stimParams:
                    param['sum'] = en[param.name()]
            else:
                self.powerWidget.setMeta('y', value=power, readonly=True)
    
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = {}
        state['daqState'] = DAQGenericTaskGui.saveState(self)
        return state
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        return DAQGenericTaskGui.restoreState(self, state['daqState'])
    
    def describe(self, params=None):
        state = self.saveState()
        ps = state['daqState']['channels']['power']
        desc = {'mode': 'power', 'command': ps['waveGeneratorWidget']}
        return desc
    
    def prepareTaskStart(self):
        ## check power before starting task.
        if self.ui.checkPowerCheck.isChecked():
            power = self.dev.outputPower()  ## request current power from laser
            valid = self.dev.checkPowerValidity(power)
            if power is None:
                raise HelpfulException("The current laser power for '%s' is unknown." % self.dev.name)
            if not valid:
                powerStr = siFormat(power, suffix='W')
                raise HelpfulException("The current laser power for '%s' (%s) is outside the expected range." % (self.dev.name(), powerStr))
    
    def generateTask(self, params=None):
        """Return a cmd dictionary suitable for passing to LaserTask."""
        
        ## Params looks like: {'amp': 7} where 'amp' is the name of a sequence parameter, and 7 is the 7th value in the list of 'amp'
        for k,v in params.items():
            if k.startswith('power.'):
                del params[k]
                params[k[6:]] = v
        rate = self.powerWidget.rate
        wave = self.powerWidget.getSingleWave(params)
        rawCmds = self.getChannelCmds(wave, rate)
        
        ### structure task in DAQGeneric-compatible way
        cmd = {}
        for k in rawCmds:
            cmd[k] = {}
            cmd[k]['command'] = rawCmds[k]
            
        cmd['powerWaveform'] = wave  ## just to allow the device task to store this data
        cmd['ignorePowerWaveform'] = True
        return  cmd
    
    def getChannelCmds(self, powerWave, rate):
        key = id(powerWave)
        if key in self.cache:
            rawCmds = self.cache[key]
        else:
            rawCmds = self.dev.getChannelCmds({'powerWaveform':powerWave}, rate) ## returns {'shutter': array(...), 'qSwitch':array(..), 'pCell':array(...)}
            self.cache[key] = rawCmds
        return rawCmds
    
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
        runSequence(lambda p: waves.append(self.powerWidget.getSingleWave(p)), params, list(params.keys())) ## appends waveforms for the entire parameter space to waves
        
        for w in waves:
            if w is not None:
                ## need to translate w into raw traces, plot them, and cache them (using id(w) as a key)
                rawWaves = self.getChannelCmds(w, rate)
                self.plotRawCurves(rawWaves, color=Qt.QColor(100, 100, 100)) ## plot the raw waveform in it's appropriate plot in grey
        
        ## calculate (or pull from cache) and display single-mode wave in red
        single = self.powerWidget.getSingleWave()
        if single is not None:
            rawSingle = self.getChannelCmds(single, rate)
            self.plotRawCurves(rawSingle, color=Qt.QColor(200, 100, 100))
                      
    def plotRawCurves(self, data, color=Qt.QColor(100, 100, 100)):
        if 'shutter' in data:
            self.shutterPlot.plot(y=data['shutter'], x=self.powerWidget.timeVals, pen=mkPen(color))
        if 'qSwitch' in data:
            self.qSwitchPlot.plot(y=data['qSwitch'], x=self.powerWidget.timeVals, pen=mkPen(color))
        if 'pCell' in data:
            self.pCellPlot.plot(y=data['pCell'], x=self.powerWidget.timeVals, pen=mkPen(color))
      
    def clearRawPlots(self):
        for p in ['shutterPlot', 'qSwitchPlot', 'pCellPlot']:
            if hasattr(self, p):
                getattr(self, p).clear()
                
    def quit(self):
        self.dev.lastResult = None
        DAQGenericTaskGui.quit(self)
