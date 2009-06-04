# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
import AOChannelTemplate, DOChannelTemplate, InputChannelTemplate
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
import numpy

class DaqChannelGui(QtGui.QWidget):
    def __init__(self, parent, name, config, plot, dev, prot):
        QtGui.QWidget.__init__(self, parent)
        
        ## Name of this channel
        self.name = name
        
        ## Configuration for this channel defined in the device configuration file
        self.config = config
        
        ## The device handle for this channel's DAQGeneric device
        self.dev = dev
        
        ## The protocol GUI window which contains this object
        self.prot = prot
        
        ## plot widget
        self.plot = plot
        plot.setCanvasBackground(QtGui.QColor(0,0,0))
        plot.replot()
        
        ## Curves displayed in self.plot
        self.plots = []
        
            
    def postUiInit(self):
        ## Automatically locate all read/writable widgets and group them together for easy 
        ## save/restore operations
        self.stateGroup = WidgetGroup(self)
        
        self.displayCheckChanged()
        QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('stateChanged(int)'), self.displayCheckChanged)
            
    def saveState(self):
        return self.stateGroup.state()
    
    def restoreState(self, state):
        return self.stateGroup.restoreState()

    def clearPlots(self):
        for i in self.plots:
            i.detach()
        self.plots = []

    def displayCheckChanged(self):
        if self.stateGroup.state()['displayCheck']:
            self.plot.show()
        else:
            self.plot.hide()
        
class OutputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        
        self.currentPlot = None
        if self.config['type'] == 'ao':
            self.ui = AOChannelTemplate.Ui_Form()
        elif self.config['type'] == 'do':
            self.ui = DOChannelTemplate.Ui_Form()
        else:
            raise Exception("Unrecognized channel type '%s'" % self.config['type'])
        self.ui.setupUi(self)
        self.postUiInit()
        self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        
        daqDev = self.dev.getDAQName(self.name)
        daqUI = self.prot.getDevice(daqDev)
        self.daqChanged(daqUI.currentState())
        
            

        QtCore.QObject.connect(daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('changed'), self.updateWaves)
        QtCore.QObject.connect(self.prot.taskThread, QtCore.SIGNAL('protocolStarted'), self.protoStarted)

        
    
    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()
        
    def listSequence(self):
        return self.ui.waveGeneratorWidget.listSequences()
    
    def generateProtocol(self, params={}):
        prot = {}
        state = self.stateGroup.state()
        if state['preSetCheck']:
            prot['preset'] = state['preSetSpin']
        if state['functionCheck']:
            prot['command'] = self.cmdScale * self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)        
        return prot
    
    def handleResult(self, result):
        pass
    
    def updateWaves(self):
        self.clearPlots()
        
        ## display sequence waves
        params = {}
        ps = self.ui.waveGeneratorWidget.listSequences()
        for k in ps:
            params[k] = range(ps[k])
        waves = []
        runSequence(lambda p: waves.append(self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, p)), params, params.keys(), passHash=True)
        for w in waves:
            if w is not None:
                self.plotCurve(w, color=QtGui.QColor(100, 100, 100), replot=False)
        
        ## display single-mode wave in red
        single = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts)
        if single is not None:
            self.plotCurve(single, color=QtGui.QColor(200, 100, 100))
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def protoStarted(self, params):
        ## Draw green trace for current command waveform
        if self.currentPlot is not None:
            self.currentPlot.detach()
        params = dict([(p[1], params[p]) for p in params if p[0] == self.dev.name])
        cur = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        self.currentPlot = self.plotCurve(cur, color=QtGui.QColor(100, 200, 100))
        
    def plotCurve(self, data, color=QtGui.QColor(100, 100, 100), replot=True):
        plot = Qwt.QwtPlotCurve('cell')
        plot.setPen(QtGui.QPen(color))
        plot.setData(self.timeVals, data)
        plot.attach(self.plot)
        self.plots.append(plot)
        if replot:
            self.plot.replot()
        return plot

class InputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.ui = InputChannelTemplate.Ui_Form()
        self.ui.setupUi(self)
        QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolStarted'), self.clearPlots)
        self.postUiInit()
                
    def listSequence(self):
        return []
    
    def generateProtocol(self, params={}):
        state = self.stateGroup.state()
        return {'record': state['recordCheck']}
    
    def handleResult(self, result):
        if self.stateGroup.state()['display']:
            plot = Qwt.QwtPlotCurve('cell')
            plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            plot.setData(result.xvals('Time'), result['scaled'])
            plot.attach(self.plot)
            self.plots.append(plot)
            self.plot.replot()
    