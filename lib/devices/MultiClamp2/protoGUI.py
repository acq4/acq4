# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from lib.devices.Device import ProtocolGui
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
import numpy
from ProtocolTemplate import *
from lib.util.debug import *
import sip

class MultiClampProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        daqDev = self.dev.getDAQName()
        self.daqUI = self.prot.getDevice(daqDev)
        
        self.traces = {}  ## Stores traces from a sequence to allow average plotting
        self.resetInpPlots = False  ## Signals result handler to clear plots before adding a new one
        self.currentCmdPlot = None
        
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        self.ui.splitter_2.setStretchFactor(0, 0)
        self.ui.splitter_2.setStretchFactor(1, 1)
        self.ui.splitter.setStretchFactor(0, 3)
        self.ui.splitter.setStretchFactor(1, 1)
        
        self.stateGroup = WidgetGroup(self)
        self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        self.unitLabels = [self.ui.waveGeneratorLabel, self.ui.holdingCheck]
        #self.modeSignalList = self.dev.listModeSignals()
        self.mode = None
        self.setMode('I=0')

        self.ui.topPlotWidget.registerPlot(self.dev.name + '.Input')
        self.ui.bottomPlotWidget.registerPlot(self.dev.name + '.Command')

        self.daqChanged(self.daqUI.currentState())
        QtCore.QObject.connect(self.daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('changed'), self.updateWaves)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.i0ModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        
    def saveState(self):
        state = self.stateGroup.state().copy()
        state['mode'] = self.getMode()
        state['primarySignal'] = str(self.ui.primarySignalCombo.currentText())
        state['secondarySignal'] = str(self.ui.secondarySignalCombo.currentText())
        return state
        
    def restoreState(self, state):
        try:
            self.setMode(state['mode'])
            self.setSignals(state['secondarySignal'], state['primarySignal'])
            self.stateGroup.setState(state)
        except:
            printExc('Error while restoring MultiClamp protocol GUI state:')
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
        for w in waves:
            if w is not None:
                self.plotCmdWave(w / self.cmdScale, color=QtGui.QColor(100, 100, 100), replot=False)
        
        ## display single-mode wave in red
        single = self.getSingleWave()
        if single is not None:
            self.plotCmdWave(single / self.cmdScale, color=QtGui.QColor(200, 100, 100))
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def clearCmdPlots(self):
        self.ui.bottomPlotWidget.clear()
        self.currentCmdPlot = None

    def protocolStarted(self):
        self.resetInpPlots = True

    def clearInpPlots(self):
        self.traces = {}
        self.ui.topPlotWidget.clear()
        
    def taskStarted(self, params):
        ## Draw green trace for current command waveform
        if self.currentCmdPlot is not None:
            self.ui.bottomPlotWidget.removeItem(self.currentCmdPlot)
        params = dict([(p[1], params[p]) for p in params if p[0] == self.dev.name])
        cur = self.getSingleWave(params) 
        if cur is not None:
            self.currentCmdPlot = self.plotCmdWave(cur / self.cmdScale, color=QtGui.QColor(100, 200, 100))
        
    def plotCmdWave(self, data, color=QtGui.QColor(100, 100, 100), replot=True):
        if data is None:
            return
        plot = self.ui.bottomPlotWidget.plot(data, x=self.timeVals)
        plot.setPen(QtGui.QPen(color))
        
        return plot
        
    def generateProtocol(self, params=None):
        state = self.stateGroup.state()
        if params is None:
            params = {}
        prot = {}
        mode = self.getMode()
        prot['mode'] = mode
        prot['recordState'] = True
        if self.ui.primarySignalCheck.isChecked():
            prot['primary'] = self.ui.primarySignalCombo.currentText()
        if self.ui.secondarySignalCheck.isChecked():
            prot['secondary'] = self.ui.secondarySignalCombo.currentText()
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
            sigs = self.dev.listSignals(mode)
            for s, c in [(sigs[0], self.ui.primarySignalCombo),(sigs[1], self.ui.secondarySignalCombo)]:
                c.clear()
                for ss in s:
                    c.addItem(ss)
            #self.ui.primarySignalCombo.clear()
            #for s in self.modeSignalList['primary'][mode]:
                #self.ui.primarySignalCombo.addItem(s)
            #self.ui.secondarySignalCombo.clear()
            #for s in self.modeSignalList['secondary'][mode]:
                #self.ui.secondarySignalCombo.addItem(s)
            
            # Disable signal, holding, and gain checks (only when switching between v and i modes)
            if mode == 'VC' or oldMode == 'VC':
                self.ui.primarySignalCheck.setChecked(False)
                self.ui.secondarySignalCheck.setChecked(False)
                self.ui.holdingCheck.setChecked(False)
                self.ui.holdingSpin.setValue(0.0)
                self.ui.setPrimaryGainCheck.setChecked(False)
                self.ui.setSecondaryGainCheck.setChecked(False)
            
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
            self.ui.topPlotWidget.setLabel('left', oldUnit)
            self.ui.bottomPlotWidget.setLabel('left', newUnit)
                
            ## Hide stim plot for I=0 mode
            if mode == 'I=0':
                self.ui.bottomPlotWidget.hide()
            else:
                self.ui.bottomPlotWidget.show()
        
        self.mode = mode
        
    def setSignals(self, pri, sec):
        for c, s in [(self.ui.primarySignalCombo, pri), (self.ui.secondarySignalCombo, sec)]:
            ind = c.findText(s)
            if ind == -1:
                raise Exception('Signal %s does not exist' % s)
            c.setCurrentIndex(ind)
        
    def handleResult(self, result, params):
        if self.resetInpPlots:
            self.resetInpPlots = False
            self.clearInpPlots()

        ## Plot the results
        plot = self.ui.topPlotWidget.plot(result['primary'].view(numpy.ndarray) / self.inpScale, x=result.xvals('Time'), params=params)
        
    def quit(self):
        ProtocolGui.quit(self)
        if not sip.isdeleted(self.daqUI):
            QtCore.QObject.disconnect(self.daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
