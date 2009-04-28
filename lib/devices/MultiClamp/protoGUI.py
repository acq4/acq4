# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
#from lib.util.generator.StimGenerator import *
from PyQt4 import Qwt5 as Qwt
import numpy

class MultiClampProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        daqDev = self.dev.getDAQName()
        daqUI = self.prot.getDevice(daqDev)
        self.cmdPlots = []
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.modeSignalList = self.dev.listModeSignals()
        self.mode = None
        self.setMode('I=0')
        self.daqChanged(daqUI.currentState())
        QtCore.QObject.connect(daqUI, QtCore.SIGNAL('changed(PyQt_PyObject)'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('changed()'), self.waveChanged)
        QtCore.QObject.connect(self.ui.updateBtn, QtCore.SIGNAL('clicked()'), self.updateWaves)
        
        
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
        return state
        
    def restoreState(self, state):
        self.setMode(state['mode'])
        try:
            self.setSignal('raw', state['rawSignal'])
            self.setSignal('scaled', state['scaledSignal'])
        except:
            sys.excepthook(*sys.exc_info())
        self.ui.scaledSignalCheck.setChecked(state['setScaledSignal'])
        self.ui.rawSignalCheck.setChecked(state['setRawSignal'])
        self.ui.setScaledGainCheck.setChecked(state['setScaledGain'])
        self.ui.scaledGainSpin.setValue(state['scaledGain'])
        self.ui.setRawGainCheck.setChecked(state['setRawGain'])
        self.ui.rawGainSpin.setValue(state['rawGain'])
        self.ui.holdingCheck.setChecked(state['setHolding'])
        self.ui.holdingSpin.setValue(state['holding'])
        
    def waveChanged(self):
        if not self.ui.autoUpdateCheck.isChecked():
            return
        self.updateWaves()
        
    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, self.numPts/self.rate, self.numPts)
        self.updateWaves()
        
    def updateWaves(self):
        ## update local sequence list
        self.paramSpace = self.ui.waveGeneratorWidget.listSequences()
        
        ## get single mode wave, cache and display
        self.singleWave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts)
        
        ## get sequence mode waves, cache and display
        
        ## plot all waves, single-mode in red
        self.clearCmdPlots()
        if self.singleWave is not None:
            self.plotCmdWave(self.singleWave, color=QtGui.QColor(200, 100, 100))
        
    def clearCmdPlots(self):
        for i in self.cmdPlots:
            i.detach()
        
    def plotCmdWave(self, data, color=QtGui.QColor(100, 100, 100)):
        plot = Qwt.QwtPlotCurve('cell')
        plot.setPen(QtGui.QPen(color))
        plot.setData(self.timeVals, data)
        plot.attach(self.ui.bottomPlotWidget)
        self.cmdPlots.append(plot)
        self.ui.bottomPlotWidget.replot()
        
    def generateProtocol(self, params={}):
        return self.currentState()
        
    def currentState(self):
        state = {}
        return state
        
    def getMode(self):
        if self.ui.icModeRadio.isChecked():
            self.mode =  'IC'
        elif self.ui.i0ModeRadio.isChecked():
            self.mode = 'I=0'
        else:
            self.mode = 'VC'
        return self.mode
        
    def setMode(self, mode):
        if mode != self.mode:
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
            
            # Disable signal checks (should only be done when switching between v and i modes)
            self.ui.scaledSignalCheck.setChecked(False)
            self.ui.rawSignalCheck.setChecked(False)
            
            # update unit labels
            
        
        
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