# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from lib.devices.Device import ProtocolGui
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
#from lib.util.generator.StimGenerator import *
from PyQt4 import Qwt5 as Qwt
import numpy
from ProtocolTemplate import *
from lib.util.PlotWidget import PlotCurve

class MultiClampProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        daqDev = self.dev.getDAQName()
        daqUI = self.prot.getDevice(daqDev)
        
        self.traces = {}  ## Stores traces from a sequence to allow average plotting
        #self.avgPlots = {}
        
        #self.cmdPlots = []
        #self.inpPlots = {}
        self.resetInpPlots = False  ## Signals result handler to clear plots before adding a new one
        self.currentCmdPlot = None
        
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = WidgetGroup(self)
        self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        #self.ui.topPlotWidget.enableAxis(PlotWidget.xBottom, False)
        self.unitLabels = [self.ui.waveGeneratorLabel, self.ui.holdingCheck]
        self.modeSignalList = self.dev.listModeSignals()
        self.mode = None
        self.setMode('I=0')

        self.ui.topPlotWidget.registerPlot(self.dev.name + '.Input')
        self.ui.bottomPlotWidget.registerPlot(self.dev.name + '.Command')


        #self.stateGroup = WidgetGroup([
            #(self.ui.scaledSignalCheck, 'setScaledSignal'),
            #(self.ui.rawSignalCheck, 'setRawSignal'),
            #(self.ui.setScaledGainCheck, 'setScaledGain'),
            #(self.ui.scaledGainSpin, 'scaledGain'),
            #(self.ui.setRawGainCheck, 'setRawGain'),
            #(self.ui.rawGainSpin, 'rawGain'),
            #(self.ui.holdingCheck, 'setHolding'),
            #(self.ui.holdingSpin, 'holding'),
            #(self.ui.splitter, 'splitter1'),
            #(self.ui.splitter_2, 'splitter2')
        #])
        
        self.daqChanged(daqUI.currentState())
        #for p in [self.ui.topPlotWidget, self.ui.bottomPlotWidget]:
            #p.setCanvasBackground(QtGui.QColor(0,0,0))
            #p.plot()
        QtCore.QObject.connect(daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('changed'), self.updateWaves)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.i0ModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolStarted'), self.sequenceStarted)
        QtCore.QObject.connect(self.prot.taskThread, QtCore.SIGNAL('taskStarted'), self.protoStarted)
        
    def saveState(self):
        state = self.stateGroup.state().copy()
        state['mode'] = self.getMode()
        state['scaledSignal'] = str(self.ui.scaledSignalCombo.currentText())
        state['rawSignal'] = str(self.ui.rawSignalCombo.currentText())
        #state['topPlot'] = self.ui.topPlotWidget.saveState()
        #state['bottomPlot'] = self.ui.bottomPlotWidget.saveState()
        #state['stim'] = self.ui.waveGeneratorWidget.saveState()
        #print state['splitter'], state['splitter_2']
        return state
        
    def restoreState(self, state):
        try:
            self.setMode(state['mode'])
            self.setSignal('raw', state['rawSignal'])
            self.setSignal('scaled', state['scaledSignal'])
            #self.ui.waveGeneratorWidget.loadState(state['stim'])
            self.stateGroup.setState(state)
        except:
            sys.excepthook(*sys.exc_info())
        self.ui.waveGeneratorWidget.update()
        
        
        
    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()
        
    def listSequence(self):
        return self.ui.waveGeneratorWidget.listSequences()

    def updateWaves(self):
        self.clearCmdPlots()
        
        ## display sequence waves
        params = {}
        ps = self.ui.waveGeneratorWidget.listSequences()
        for k in ps:
            params[k] = range(ps[k])
        waves = []
        runSequence(lambda p: waves.append(self.getSingleWave(p)), params, params.keys(), passHash=True)
        #runSequence(lambda p: waves.append(self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, p)), params, params.keys(), passHash=True)
        for w in waves:
            if w is not None:
                self.plotCmdWave(w / self.cmdScale, color=QtGui.QColor(100, 100, 100), replot=False)
        
        ## display single-mode wave in red
        #single = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts)
        single = self.getSingleWave()
        if single is not None:
            self.plotCmdWave(single / self.cmdScale, color=QtGui.QColor(200, 100, 100))
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def clearCmdPlots(self):
        #for i in self.cmdPlots:
            #i.detach()
        #self.cmdPlots = []
        self.ui.bottomPlotWidget.clear()
        self.currentCmdPlot = None

    def sequenceStarted(self):
        self.resetInpPlots = True

    def clearInpPlots(self):
        #for k in self.inpPlots:
            #for i in self.inpPlots[k]:
                #i.detach()
        #self.inpPlots = {}
        #for i in self.avgPlots:
            #self.avgPlots[i].detach()
        #self.avgPlots = {}
        self.traces = {}
        self.ui.topPlotWidget.clear()
        
    def protoStarted(self, params):
        ## Draw green trace for current command waveform
        if self.currentCmdPlot is not None:
            self.ui.bottomPlotWidget.detachCurve(self.currentCmdPlot)
            #self.currentCmdPlot.detach()
        params = dict([(p[1], params[p]) for p in params if p[0] == self.dev.name])
        #cur = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        cur = self.getSingleWave(params) 
        if cur is not None:
            self.currentCmdPlot = self.plotCmdWave(cur / self.cmdScale, color=QtGui.QColor(100, 200, 100))
        
    def plotCmdWave(self, data, color=QtGui.QColor(100, 100, 100), replot=True):
        if data is None:
            return
        plot = self.ui.bottomPlotWidget.plot(data, x=self.timeVals, replot=False)
        #plot = PlotCurve('cell')
        plot.setPen(QtGui.QPen(color))
        #plot.setData(self.timeVals, data)
        #plot.attach(self.ui.bottomPlotWidget)
        #self.cmdPlots.append(plot)
        if replot:
            self.ui.bottomPlotWidget.replot()
        
        return plot
        
    def generateProtocol(self, params=None):
        state = self.stateGroup.state()
        if params is None:
            params = {}
        prot = {}
        mode = self.getMode()
        prot['mode'] = mode
        prot['recordState'] = True
        if self.ui.scaledSignalCheck.isChecked():
            prot['scaled'] = self.ui.scaledSignalCombo.currentText()
        if self.ui.rawSignalCheck.isChecked():
            prot['raw'] = self.ui.rawSignalCombo.currentText()
        if mode != 'I=0':
            ## Must scale command to V or A before sending to protocol system.
            wave = self.getSingleWave(params)
            if wave is not None:
                prot['command'] = wave
            if state['holdingCheck']:
                prot['holding'] = state['holdingSpin']
        return prot
    
    def getSingleWave(self, params=None):
        state = self.stateGroup.state()
        if state['holdingCheck']:
            h = state['holdingSpin']
        else:
            h = 0.0
        self.ui.waveGeneratorWidget.setOffset(h)
        self.ui.waveGeneratorWidget.setScale(self.cmdScale)
        ## waveGenerator generates values in V or A
        wave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        
        if wave is None:
            return None
        #if state['holdingCheck']:
            #wave += (state['holdingSpin'] / self.cmdScale)
        return wave
        
        
    def getMode(self):
        if self.ui.icModeRadio.isChecked():
            self.mode =  'IC'
        elif self.ui.i0ModeRadio.isChecked():
            self.mode = 'I=0'
        else:
            self.mode = 'VC'
        return self.mode
        
    def setMode(self, mode=None):
        if mode != self.mode:
            oldMode = self.mode
            if mode is None:
                mode = self.getMode()
            # set radio button
            if mode == 'IC':
                self.ui.icModeRadio.setChecked(True)
            elif mode == 'I=0':
                self.ui.i0ModeRadio.setChecked(True)
            else:
                self.ui.vcModeRadio.setChecked(True)
            
            # update signal lists
            self.ui.scaledSignalCombo.clear()
            for s in self.modeSignalList['scaled'][mode]:
                self.ui.scaledSignalCombo.addItem(s)
            self.ui.rawSignalCombo.clear()
            for s in self.modeSignalList['raw'][mode]:
                self.ui.rawSignalCombo.addItem(s)
            
            # Disable signal, holding, and gain checks (only when switching between v and i modes)
            if mode == 'VC' or oldMode == 'VC':
                self.ui.scaledSignalCheck.setChecked(False)
                self.ui.rawSignalCheck.setChecked(False)
                self.ui.holdingCheck.setChecked(False)
                self.ui.holdingSpin.setValue(0.0)
                self.ui.setScaledGainCheck.setChecked(False)
                self.ui.setRawGainCheck.setChecked(False)
            
            # update unit labels and scaling
            if mode == 'VC':
                newUnit = 'mV'
                oldUnit = 'pA'
                self.cmdScale = 1e-3
                self.inpScale = 1e-12
            else:
                newUnit = 'pA'
                oldUnit = 'mV'
                self.cmdScale = 1e-12
                self.inpScale = 1e-3
            self.stateGroup.setScale(self.ui.holdingSpin, 1./self.cmdScale)
            #self.ui.waveGeneratorWidget.setScale(self.cmdScale)
            for l in self.unitLabels:
                text = str(l.text())
                l.setText(text.replace(oldUnit, newUnit))
            self.ui.topPlotWidget.setAxisTitle(PlotWidget.yLeft, oldUnit)
            self.ui.bottomPlotWidget.setAxisTitle(PlotWidget.yLeft, newUnit)
                
            ## Hide stim plot for I=0 mode
            if mode == 'I=0':
                self.ui.bottomPlotWidget.hide()
            else:
                self.ui.bottomPlotWidget.show()
        
        self.mode = mode
        
    def setSignal(self, chan, sig):
        if chan == 'scaled':
            c = self.ui.scaledSignalCombo
        else:
            c = self.ui.rawSignalCombo
        ind = c.findText(sig)
        if ind == -1:
            raise Exception('Signal %s does not exist' % sig)
        c.setCurrentIndex(ind)
        
    def handleResult(self, result, params):
        if self.resetInpPlots:
            self.resetInpPlots = False
            self.clearInpPlots()

        ## Is this result one of repeated trials?
        #params = params.copy()
        #repsRunning = ('protocol', 'repetitions') in params
        
        ## What is the total number of repeats?
        #reps = self.prot.getParam('repetitions')
        #if reps == 0:
            #reps = 1
            
        ## What is the current repetition number?
        #rep = 1
        #if repsRunning:
            #rep += params[('protocol', 'repetitions')]
            #del params[('protocol', 'repetitions')]
        #paramKey = tuple(params.items())
            
        #if repsRunning:
            #plotColor = QtGui.QColor(255, 255, 255, int(255./rep))
        #else:
            #plotColor = QtGui.QColor(255, 255, 255, 200)
        
        #if repsRunning and (reps > 1):
            ## Add the results into the average plot if requested
                
            #if self.stateGroup.state()['displayAverageCheck'] and repsRunning:
                
                #if paramKey not in self.traces:
                    #self.traces[paramKey] = []
                #self.traces[paramKey].append(result)
                
                #for k in self.traces:
                    #if k not in self.avgPlots:
                        #plot = self.ui.topPlotWidget.plot(replot=False)
                        ##plot = PlotCurve('cell')
                        #plot.setPen(QtGui.QPen(QtGui.QColor(0, 255, 0)))
                        #plot.setZ(100)
                        #self.avgPlots[k] = plot
                        ##plot.attach(self.ui.topPlotWidget)
                    #avgTrace = numpy.vstack([a['scaled'].view(ndarray) for a in self.traces[k]]).mean(axis=0)
                    ##print avgTrace.shape
                    #self.avgPlots[k].setData(self.traces[k][0].xvals('Time'), avgTrace / self.inpScale)
                
        ## Plot the results
        plot = self.ui.topPlotWidget.plot(result['scaled'].view(numpy.ndarray) / self.inpScale, x=result.xvals('Time'), params=params)
        #plot = PlotCurve('cell')
        #plot.setData(result.xvals('Time'), result['scaled'] / self.inpScale)
        #plot.attach(self.ui.topPlotWidget)
        #if paramKey not in self.inpPlots:
            #self.inpPlots[paramKey] = []
        #self.inpPlots[paramKey].append(plot)
        
        ## Update the color of all plots sharing this parameter set
        #alpha = 200 / len(self.inpPlots[paramKey])
        #for p in self.inpPlots[paramKey]:
            #p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, alpha)))
        
        
        #self.ui.topPlotWidget.replot()
        