# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.util import Qt
from . import AOChannelTemplate, DOChannelTemplate, InputChannelTemplate
from acq4.util.SequenceRunner import *
import numpy
import weakref
from acq4.pyqtgraph import siFormat, SpinBox, WidgetGroup

###### For task GUIs

class DaqChannelGui(Qt.QWidget):
    def __init__(self, parent, name, config, plot, dev, taskRunner, daqName=None):
        Qt.QWidget.__init__(self, parent)
        
        ## Name of this channel
        self.name = name
        
        ## Parent taskGui object
        self.taskGui = weakref.ref(parent)
        
        ## Configuration for this channel defined in the device configuration file
        self.config = config
        
        self.scale = 1.0
        self.units = ''
        
        ## The device handle for this channel's DAQGeneric device
        self.dev = dev
        
        ## The task GUI window which contains this object
        self.taskRunner = weakref.ref(taskRunner)
        
        ## Make sure task interface includes our DAQ device
        if daqName is None:
            self.daqDev = self.dev.getDAQName(self.name)
        else:
            self.daqDev = daqName
        self.daqUI = self.taskRunner().getDevice(self.daqDev)
        
        ## plot widget
        self.plot = plot
        self.plot.setDownsampling(ds=True, auto=True, mode='peak')
        self.plot.setClipToView(True)
            
    def postUiInit(self):
        ## Automatically locate all read/writable widgets and group them together for easy 
        ## save/restore operations
        self.stateGroup = WidgetGroup(self)
        self.stateGroup.addWidget(self.plot, name='plot')
        
        self.displayCheckChanged()
        self.ui.displayCheck.stateChanged.connect(self.displayCheckChanged)
        
        if 'units' in self.config:
            self.setUnits(self.config['units'])
        else:
            self.setUnits('')
            
    def updateTitle(self):
        self.ui.groupBox.setTitle(self.name + " (%s)" %self.units)
    
    def setUnits(self, units):
        self.units = units
        for s in self.getSpins():
            if isinstance(s, SpinBox):
                s.setOpts(suffix=units)
        self.updateTitle()

    def getSpins(self):
        return []

    def setChildrenVisible(self, obj, vis):
        for c in obj.children():
            if isinstance(c, Qt.QWidget):
                c.setVisible(vis)
            else:
                self.setChildrenVisible(c, vis)
            
    def saveState(self):
        return self.stateGroup.state()
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        if hasattr(self.ui, 'waveGeneratorWidget'):
            self.ui.waveGeneratorWidget.update()

    def clearPlots(self):
        self.plot.clear()
        self.currentPlot = None

    def displayCheckChanged(self):
        if self.stateGroup.state()['displayCheck']:
            self.plot.show()
        else:
            self.plot.hide()
            
    def taskStarted(self, params):
        pass
    
    def taskSequenceStarted(self):
        pass
    
    def quit(self):
        #print "quit DAQGeneric channel", self.name
        self.plot.close()
        
        
class OutputChannelGui(DaqChannelGui):
    
    sigSequenceChanged = Qt.Signal(object)
    sigDataChanged = Qt.Signal(object)
    
    def __init__(self, *args):
        self._block_update = False  # blocks plotting during state changes
        DaqChannelGui.__init__(self, *args)
        self.units = ''
        self.currentPlot = None
        if self.config['type'] == 'ao':
            self.ui = AOChannelTemplate.Ui_Form()
        elif self.config['type'] == 'do':
            self.ui = DOChannelTemplate.Ui_Form()
        else:
            raise Exception("Unrecognized channel type '%s'" % self.config['type'])
        self.ui.setupUi(self)
        self.postUiInit()
        
        self.daqChanged(self.daqUI.currentState())
        
        if self.config['type'] == 'ao':
            for s in self.getSpins():
                s.setOpts(dec=True, bounds=[None, None], step=1.0, minStep=1e-12, siPrefix=True)

        self.daqUI.sigChanged.connect(self.daqChanged)
        self.ui.waveGeneratorWidget.sigDataChanged.connect(self.updateWaves)
        self.ui.waveGeneratorWidget.sigFunctionChanged.connect(self.waveFunctionChanged)
        self.ui.waveGeneratorWidget.sigParametersChanged.connect(self.sequenceChanged)
        self.ui.holdingCheck.stateChanged.connect(self.holdingCheckChanged)
        self.ui.holdingSpin.valueChanged.connect(self.holdingSpinChanged)
        self.ui.functionCheck.toggled.connect(self.functionCheckToggled)
        self.dev.sigHoldingChanged.connect(self.updateHolding)
        
        self.holdingCheckChanged()
        self.ui.functionCheck.setChecked(True)

    def getSpins(self):
        return (self.ui.preSetSpin, self.ui.holdingSpin)
    
    def setMeta(self, key, **kwargs):
        ## key is 'x' (time), 'y' (amp), or 'xy' (sum)
        self.ui.waveGeneratorWidget.setMeta(key, **kwargs)
        
    def setUnits(self, units, **kwargs):
        DaqChannelGui.setUnits(self, units)
        self.ui.waveGeneratorWidget.setMeta('y', units=units, siPrefix=True, **kwargs)
        
    def quit(self):
        DaqChannelGui.quit(self)
        
        try:
            self.daqUI.sigChanged.disconnect(self.daqChanged)
        except TypeError:
            pass
        self.ui.waveGeneratorWidget.sigDataChanged.disconnect(self.updateWaves)
        self.ui.waveGeneratorWidget.sigFunctionChanged.disconnect(self.waveFunctionChanged)
        self.ui.waveGeneratorWidget.sigParametersChanged.disconnect(self.sequenceChanged)
        self.ui.holdingCheck.stateChanged.disconnect(self.holdingCheckChanged)
        self.ui.holdingSpin.valueChanged.disconnect(self.holdingSpinChanged)
        self.dev.sigHoldingChanged.disconnect(self.updateHolding)

    def functionCheckToggled(self, checked):
        if checked:
            self.ui.waveGeneratorWidget.setEnabled(True)
            self.updateWaves()
        else:
            self.ui.waveGeneratorWidget.setEnabled(False)
            self.updateWaves()

    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()
        
    def listSequence(self):
        return self.ui.waveGeneratorWidget.listSequences()
    
    def sequenceChanged(self):
        self.sigSequenceChanged.emit(self.dev.name())
    
    def generateTask(self, params=None):
        if params is None:
            params = {}
        prot = {}
        state = self.stateGroup.state()
        if state['preSetCheck']:
            prot['preset'] = state['preSetSpin']
        if state['holdingCheck']:
            prot['holding'] = state['holdingSpin']
        if state['functionCheck']:
            prot['command'] = self.getSingleWave(params)
            
        return prot
    
    def handleResult(self, result, params):
        pass
    
    def updateWaves(self):
        if self._block_update:
            return
        if not self.ui.functionCheck.isChecked():
            self.plot.clear()
            return

        self.clearPlots()
        
        ## display sequence waves
        params = {}
        ps = self.ui.waveGeneratorWidget.listSequences()
        for k in ps:
            params[k] = range(len(ps[k]))
        waves = []
        runSequence(lambda p: waves.append(self.getSingleWave(p)), params, list(params.keys())) ## appends waveforms for the entire parameter space to waves

        autoRange = self.plot.getViewBox().autoRangeEnabled()
        self.plot.enableAutoRange(x=False, y=False)
        try:
            for w in waves:
                if w is not None:
                    # self.ui.functionCheck.setChecked(True)
                    self.plotCurve(w, color=Qt.QColor(100, 100, 100))
            
            ## display single-mode wave in red
            single = self.getSingleWave()
            if single is not None:
                # self.ui.functionCheck.setChecked(True)
                self.plotCurve(single, color=Qt.QColor(200, 100, 100))
        finally:
            self.plot.enableAutoRange(x=autoRange[0], y=autoRange[1])

        self.sigDataChanged.emit(self)
        
    def taskStarted(self, params):
        ## Draw green trace for current command waveform
        if not self.stateGroup.state()['displayCheck']:
            return
        if self.currentPlot is not None:
            self.plot.removeItem(self.currentPlot)
        
        cur = self.getSingleWave(params)
        if cur is not None:
            self.currentPlot = self.plotCurve(cur, color=Qt.QColor(100, 200, 100))
            self.currentPlot.setZValue(100)
        
    def plotCurve(self, data, color=Qt.QColor(100, 100, 100), replot=True):
        plot = self.plot.plot(y=data, x=self.timeVals, pen=Qt.QPen(color))
        return plot

    def getSingleWave(self, params=None):
        state = self.stateGroup.state()
        h = self.getHoldingValue()
        if h is not None:
            self.ui.waveGeneratorWidget.setOffset(h)
        
        wave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        
        return wave
        
    def holdingCheckChanged(self, *v):
        self.ui.holdingSpin.setEnabled(self.ui.holdingCheck.isChecked())
        self.updateHolding()
        
    def holdingSpinChanged(self, *args):
        hv = self.getHoldingValue()
        if hv is not None:
            self.ui.waveGeneratorWidget.setOffset(hv)
        
        
    def updateHolding(self):
        hv = self.getHoldingValue()
        if hv is not None:
            if not self.ui.holdingCheck.isChecked():
                self.ui.holdingSpin.setValue(hv)
            self.ui.waveGeneratorWidget.setOffset(hv)
            
    def getHoldingValue(self):
        """Return the value for this channel that will be used when the task is run
        (by default, this is just the current holding value)"""
        if self.ui.holdingCheck.isChecked():
            return self.ui.holdingSpin.value()
        else:
            return self.taskGui().getChanHolding(self.name)
        
    def waveFunctionChanged(self):
        if self.ui.waveGeneratorWidget.functionString() != "":
            self.ui.functionCheck.setChecked(True)
        else:
            self.ui.functionCheck.setChecked(False)
            
    def restoreState(self, state):
        block = self._block_update
        self._block_update = True
        try:
            DaqChannelGui.restoreState(self, state)
        finally:
            self._block_update = False
            
        self.updateWaves()
        
class InputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.ui = InputChannelTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.postUiInit()
        self.clearBeforeNextPlot = False
         
    def taskSequenceStarted(self):
        self.clearBeforeNextPlot = True
        #self.clearPlots()
         
    def listSequence(self):
        return []
    
    def generateTask(self, params=None):
        if params is None:
            params = {}
        state = self.stateGroup.state()
        return {'record': state['recordCheck'], 'recordInit': state['recordInitCheck']}
    
    def handleResult(self, result, params):
        if self.stateGroup.state()['displayCheck']:
            if self.clearBeforeNextPlot:
                self.clearPlots()
                self.clearBeforeNextPlot = False

            plot = self.plot.plot(y=result.view(numpy.ndarray), x=result.xvals('Time'), pen=Qt.QPen(Qt.QColor(200, 200, 200)), params=params)
            #plot = PlotCurve('cell')
            #plot.setPen(Qt.QPen(Qt.QColor(200, 200, 200)))
            #plot.setData(result.xvals('Time'), result)
            #plot.attach(self.plot)
            #self.plots.append(plot)
            #self.plot.replot()
    
