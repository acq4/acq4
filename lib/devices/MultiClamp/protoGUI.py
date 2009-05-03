# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
from lib.util.SequenceRunner import *
#from lib.util.generator.StimGenerator import *
from PyQt4 import Qwt5 as Qwt
import numpy

class MultiClampProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        daqDev = self.dev.getDAQName()
        daqUI = self.prot.getDevice(daqDev)
        self.cmdPlots = []
        self.inpPlots = []
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.unitLabels = [self.ui.waveGeneratorLabel, self.ui.holdingCheck]
        self.modeSignalList = self.dev.listModeSignals()
        self.mode = None
        self.setMode('I=0')
        self.daqChanged(daqUI.currentState())
        for p in [self.ui.topPlotWidget, self.ui.bottomPlotWidget]:
            p.setCanvasBackground(QtGui.QColor(0,0,0))
            p.replot()
        QtCore.QObject.connect(daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('functionChanged()'), self.waveFuncChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('sequenceChanged()'), self.waveSeqChanged)
        QtCore.QObject.connect(self.ui.updateBtn, QtCore.SIGNAL('clicked()'), self.updateWaves)
        QtCore.QObject.connect(self.ui.vcModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.icModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.ui.i0ModeRadio, QtCore.SIGNAL('clicked()'), self.setMode)
        QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolStarted()'), self.clearInpPlots)
        
    def saveState(self):
        state = {}
        state['mode'] = self.getMode()
        state['scaledSignal'] = str(self.ui.scaledSignalCombo.currentText())
        state['rawSignal'] = str(self.ui.rawSignalCombo.currentText())
        state['setScaledSignal'] = self.ui.scaledSignalCheck.isChecked()
        state['setRawSignal'] = self.ui.rawSignalCheck.isChecked()
        state['setScaledGain'] = self.ui.setScaledGainCheck.isChecked()
        state['scaledGain'] = self.ui.scaledGainSpin.value()
        state['setRawGain'] = self.ui.setRawGainCheck.isChecked()
        state['rawGain'] = self.ui.rawGainSpin.value()
        state['setHolding'] = self.ui.holdingCheck.isChecked()
        state['holding'] = self.ui.holdingSpin.value()
        state['stim'] = self.ui.waveGeneratorWidget.saveState()
        state['splitter1'] = str(self.ui.splitter.saveState().toPercentEncoding())
        state['splitter2'] = str(self.ui.splitter_2.saveState().toPercentEncoding())
        return state
        
    def restoreState(self, state):
        try:
            self.setMode(state['mode'])
            self.setSignal('raw', state['rawSignal'])
            self.setSignal('scaled', state['scaledSignal'])
            self.ui.scaledSignalCheck.setChecked(state['setScaledSignal'])
            self.ui.rawSignalCheck.setChecked(state['setRawSignal'])
            self.ui.setScaledGainCheck.setChecked(state['setScaledGain'])
            self.ui.scaledGainSpin.setValue(state['scaledGain'])
            self.ui.setRawGainCheck.setChecked(state['setRawGain'])
            self.ui.rawGainSpin.setValue(state['rawGain'])
            self.ui.holdingCheck.setChecked(state['setHolding'])
            self.ui.holdingSpin.setValue(state['holding'])
            self.ui.waveGeneratorWidget.loadState(state['stim'])
            self.ui.splitter.restoreState(QtCore.QByteArray.fromPercentEncoding(state['splitter1']))
            self.ui.splitter_2.restoreState(QtCore.QByteArray.fromPercentEncoding(state['splitter2']))
        except:
            sys.excepthook(*sys.exc_info())
        self.updateWaves()
        
    def waveFuncChanged(self):
        if not self.ui.autoUpdateCheck.isChecked():
            return
        self.updateWaves()
        
    def waveSeqChanged(self):
        self.waveFuncChanged()
        #self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
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
        runSequence(lambda p: waves.append(self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, p)), params, params.keys(), passHash=True)
        for w in waves:
            if w is not None:
                self.plotCmdWave(w, color=QtGui.QColor(100, 100, 100), replot=False)
        
        ## display single-mode wave in red
        single = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts)
        if single is not None:
            self.plotCmdWave(single, color=QtGui.QColor(200, 100, 100))
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def clearCmdPlots(self):
        for i in self.cmdPlots:
            i.detach()
        self.cmdPlots = []
        
    def clearInpPlots(self):
        for i in self.inpPlots:
            i.detach()
        self.inpPlots = []
        
    def plotCmdWave(self, data, color=QtGui.QColor(100, 100, 100), replot=True):
        plot = Qwt.QwtPlotCurve('cell')
        plot.setPen(QtGui.QPen(color))
        plot.setData(self.timeVals, data)
        plot.attach(self.ui.bottomPlotWidget)
        self.cmdPlots.append(plot)
        if replot:
            self.ui.bottomPlotWidget.replot()
        
    def generateProtocol(self, params={}):
        prot = {}
        mode = self.getMode()
        prot['mode'] = mode
        prot['recordState'] = True
        if self.ui.scaledSignalCheck.isChecked():
            prot['scaled'] = self.ui.scaledSignalCombo.currentText()
        if self.ui.rawSignalCheck.isChecked():
            prot['raw'] = self.ui.rawSignalCombo.currentText()
        if mode != 'I=0':
            prot['command'] = self.cmdScale * self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        return prot
    
        
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
                self.ui.setScaledGainCheck.setChecked(False)
                self.ui.setRawGainCheck.setChecked(False)
            
            # update unit labels and scaling
            if mode == 'VC':
                newUnit = 'mV'
                oldUnit = 'pA'
                self.cmdScale = 1e-3
            else:
                newUnit = 'pA'
                oldUnit = 'mV'
                self.cmdScale = 1e-12
            for l in self.unitLabels:
                text = str(l.text())
                l.setText(text.replace(oldUnit, newUnit))
                
        
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
        
    def handleResult(self, result, dataManager):
        plot = Qwt.QwtPlotCurve('cell')
        plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        plot.setData(result.xvals('Time'), result['scaled'])
        plot.attach(self.ui.topPlotWidget)
        self.inpPlots.append(plot)
        self.ui.topPlotWidget.replot()
        