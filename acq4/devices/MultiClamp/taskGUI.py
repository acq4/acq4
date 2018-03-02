# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import sys
from acq4.devices.Device import TaskGui
from acq4.util.SequenceRunner import *
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
import numpy
from .TaskTemplate import *
from acq4.util.debug import *
import sip

class MultiClampTaskGui(TaskGui):
    
    #sigSequenceChanged = Qt.Signal(object)  ## defined upstream
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        daqDev = self.dev.getDAQName()
        self.daqUI = self.taskRunner.getDevice(daqDev)
        
        self.traces = {}  ## Stores traces from a sequence to allow average plotting
        self.resetInpPlots = False  ## Signals result handler to clear plots before adding a new one
        self.currentCmdPlot = None
        self._block_update = False  # blocks plotting during state changes
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        self.ui.splitter_2.setStretchFactor(0, 0)
        self.ui.splitter_2.setStretchFactor(1, 1)
        self.ui.splitter.setStretchFactor(0, 3)
        self.ui.splitter.setStretchFactor(1, 1)
        
        self.stateGroup = WidgetGroup(self)
        #self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        self.ui.waveGeneratorWidget.setMeta('x', units='s', siPrefix=True, dec=True, step=0.5, minStep=1e-6)
        self.unitLabels = [self.ui.waveGeneratorLabel, self.ui.holdingCheck]
        #self.modeSignalList = self.dev.listModeSignals()
        self.mode = None
        self.setMode('I=0')

        self.ui.topPlotWidget.registerPlot(self.dev.name() + '.Input')
        self.ui.topPlotWidget.setDownsampling(ds=True, auto=True, mode='peak')
        self.ui.topPlotWidget.setClipToView(True)
        self.ui.bottomPlotWidget.registerPlot(self.dev.name() + '.Command')
        self.ui.bottomPlotWidget.setDownsampling(ds=True, auto=True, mode='peak')
        self.ui.bottomPlotWidget.setClipToView(True)

        self.daqChanged(self.daqUI.currentState())
        self.daqUI.sigChanged.connect(self.daqChanged)
        self.ui.waveGeneratorWidget.sigDataChanged.connect(self.updateWaves)
        self.ui.waveGeneratorWidget.sigParametersChanged.connect(self.sequenceChanged)
        self.stateGroup.sigChanged.connect(self.uiStateChanged)
        self.dev.sigStateChanged.connect(self.devStateChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.uiStateChanged('', '')
        self.devStateChanged()
        
    def uiStateChanged(self, name, value):
        if 'ModeRadio' in name:
            self.setMode()
        
        if self.getMode() == 'I=0':
            self.ui.holdingCheck.setChecked(False)
            self.ui.holdingCheck.setEnabled(False)
        else:
            self.ui.holdingCheck.setEnabled(True)
            
        checkMap = {
            'holdingCheck': self.ui.holdingSpin,
            'primarySignalCheck': self.ui.primarySignalCombo,
            'secondarySignalCheck': self.ui.secondarySignalCombo,
            'primaryGainCheck': self.ui.primaryGainSpin,
            'secondaryGainCheck': self.ui.secondaryGainSpin,
        }
        
        ## For each check box, enable its corresponding control
        if name in checkMap:
            checkMap[name].setEnabled(value)
            self.devStateChanged()

    def devStateChanged(self, state=None):
        mode = self.getMode()
        state = self.dev.getLastState(mode)
        
        if not self.ui.holdingSpin.isEnabled():
            self.ui.holdingSpin.setValue(state['holding'])
        if not self.ui.primaryGainSpin.isEnabled():
            self.ui.primaryGainSpin.setValue(state['primaryGain'])
        if not self.ui.secondaryGainSpin.isEnabled():
            self.ui.secondaryGainSpin.setValue(state['secondaryGain'])
            
        psig = ssig = None
        if not self.ui.primarySignalCombo.isEnabled():
            psig = state['primarySignal']
        if not self.ui.secondarySignalCombo.isEnabled():
            ssig = state['secondarySignal']
        self.setSignals(psig, ssig)

    def devHoldingChanged(self, dev, mode):
        if mode != self.getMode():
            return
        if not self.ui.holdingSpin.isEnabled():
            state = self.dev.getLastState(mode)
            self.ui.holdingSpin.setValue(state['holding'])

    def saveState(self):
        state = self.stateGroup.state().copy()
        state['mode'] = self.getMode()
        state['primarySignal'] = str(self.ui.primarySignalCombo.currentText())
        state['secondarySignal'] = str(self.ui.secondarySignalCombo.currentText())
        return state
        
    def restoreState(self, state):
        block = self._block_update
        try:
            self._block_update = True
            self.setMode(state['mode'])
            if 'primarySignal' in state and 'secondarySignal' in state:
                self.setSignals(state['primarySignal'], state['secondarySignal'])
            self.stateGroup.setState(state)
            self.devStateChanged()
        except:
            printExc('Error while restoring MultiClamp task GUI state:')
        finally:
            self._block_update = block
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

    def updateWaves(self):
        if self._block_update:
            return

        self.clearCmdPlots()
        
        ## compute sequence waves
        params = {}
        ps = self.ui.waveGeneratorWidget.listSequences()
        for k in ps:
            params[k] = range(len(ps[k]))
        waves = []
        runSequence(lambda p: waves.append(self.getSingleWave(p)), params, list(params.keys()))

        # Plot all waves but disable auto-range first to improve performance.
        autoRange = self.ui.bottomPlotWidget.getViewBox().autoRangeEnabled()
        self.ui.bottomPlotWidget.enableAutoRange(x=False, y=False)
        try:
            for w in waves:
                if w is not None:
                    self.plotCmdWave(w, color=Qt.QColor(100, 100, 100), replot=False)
        
            ## display single-mode wave in red
            single = self.getSingleWave()
            if single is not None:
                p = self.plotCmdWave(single, color=Qt.QColor(200, 100, 100))
                p.setZValue(1000)

        finally:
            # re-enable auto range if needed
            self.ui.bottomPlotWidget.enableAutoRange(x=autoRange[0], y=autoRange[1])
        
    def clearCmdPlots(self):
        self.ui.bottomPlotWidget.clear()
        self.currentCmdPlot = None

    def taskSequenceStarted(self):
        self.resetInpPlots = True

    def clearInpPlots(self):
        self.traces = {}
        self.ui.topPlotWidget.clear()
        
    def taskStarted(self, params):
        ## Draw green trace for current command waveform
        if self.currentCmdPlot is not None:
            self.ui.bottomPlotWidget.removeItem(self.currentCmdPlot)
        params = dict([(p[1], params[p]) for p in params if p[0] == self.dev.name()])
        cur = self.getSingleWave(params) 
        if cur is not None:
            self.currentCmdPlot = self.plotCmdWave(cur, color=Qt.QColor(100, 200, 100))
            self.currentCmdPlot.setZValue(1001)
        
    def plotCmdWave(self, data, color=Qt.QColor(100, 100, 100), replot=True):
        if data is None:
            return
        plot = self.ui.bottomPlotWidget.plot(data, x=self.timeVals)
        plot.setPen(Qt.QPen(color))
        
        return plot
        
    def generateTask(self, params=None):
        state = self.stateGroup.state()
        if params is None:
            params = {}
        task = {}
        mode = self.getMode()
        task['mode'] = mode
        task['recordState'] = True
        #if self.ui.primarySignalCheck.isChecked():
            #task['primary'] = self.ui.primarySignalCombo.currentText()
        #if self.ui.secondarySignalCheck.isChecked():
            #task['secondary'] = self.ui.secondarySignalCombo.currentText()
        if state['primarySignalCheck']:
            task['primarySignal'] = state['primarySignalCombo']
        if state['secondarySignalCheck']:
            task['secondarySignal'] = state['secondarySignalCombo']
        if state['primaryGainCheck']:
            task['primaryGain'] = state['primaryGainSpin']
        if state['secondaryGainCheck']:
            task['secondaryGain'] = state['secondaryGainSpin']
        if mode != 'I=0':
            ## Must scale command to V or A before sending to task system.
            wave = self.getSingleWave(params)
            if wave is not None:
                task['command'] = wave
            if state['holdingCheck']:
                task['holding'] = state['holdingSpin']
        #print "Task:", task
        return task
    
    def getSingleWave(self, params=None):
        state = self.stateGroup.state()
        h = state['holdingSpin']
        self.ui.waveGeneratorWidget.setOffset(h)
        ## waveGenerator generates values in V or A
        wave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        
        if wave is None:
            return None
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
                #print "Set mode to", mode
            # set radio button
            if mode == 'IC':
                self.ui.icModeRadio.setChecked(True)
            elif mode == 'I=0':
                self.ui.i0ModeRadio.setChecked(True)
            else:
                self.ui.vcModeRadio.setChecked(True)
            
            # update signal lists
            self.stateGroup.blockSignals(True)
            sigs = self.dev.listSignals(mode)
            #print "Signals:", sigs
            #print "-------"
            for s, c in [(sigs[0], self.ui.primarySignalCombo),(sigs[1], self.ui.secondarySignalCombo)]:
                c.clear()
                for ss in s:
                    c.addItem(ss)
            self.stateGroup.blockSignals(False)
            
            # Disable signal, holding, and gain checks (only when switching between v and i modes)
            if mode == 'VC' or oldMode == 'VC':
                self.ui.primarySignalCheck.setChecked(False)
                self.ui.secondarySignalCheck.setChecked(False)
                self.ui.holdingCheck.setChecked(False)
                self.ui.primaryGainCheck.setChecked(False)
                self.ui.secondaryGainCheck.setChecked(False)
                self.devStateChanged()
            
            # update unit labels and scaling
            if mode == 'VC':
                newUnit = 'V'
                oldUnit = 'A'
                spinOpts = dict(suffix='V', siPrefix=True, dec=True, step=0.5, minStep=1e-3)
                self.ui.waveGeneratorWidget.setMeta('y', **spinOpts)
                self.ui.waveGeneratorWidget.setMeta('xy', units='V*s', siPrefix=True, dec=True, step=0.5, minStep=1e-6)
            else:
                newUnit = 'A'
                oldUnit = 'V'
                spinOpts = dict(suffix='A', siPrefix=True, dec=True, step=0.5, minStep=1e-12)
                self.ui.waveGeneratorWidget.setMeta('y', **spinOpts)
                self.ui.waveGeneratorWidget.setMeta('xy', units='C', siPrefix=True, dec=True, step=0.5, minStep=1e-15)
            self.ui.holdingSpin.setOpts(**spinOpts)
            for l in self.unitLabels:
                text = str(l.text())
                l.setText(text.replace(oldUnit, newUnit))
            self.ui.topPlotWidget.setLabel('left', units=oldUnit)
            self.ui.bottomPlotWidget.setLabel('left', units=newUnit)
                
            ## Hide stim plot for I=0 mode
            if mode == 'I=0':
                self.ui.bottomPlotWidget.hide()
            else:
                self.ui.bottomPlotWidget.show()
        
            self.devStateChanged()
        
        self.mode = mode
        
    def setSignals(self, pri, sec):
        #print "setSignals", pri, sec
        for c, s in [(self.ui.primarySignalCombo, pri), (self.ui.secondarySignalCombo, sec)]:
            if s is None:
                continue
            ind = c.findText(s)
            if ind == -1:
                for i in range(c.count()):
                    print(c.itemText(i))
                raise Exception('Signal "%s" does not exist' % s)
            c.setCurrentIndex(ind)
        
    def handleResult(self, result, params):
        if self.resetInpPlots:
            self.resetInpPlots = False
            self.clearInpPlots()

        ## Plot the results
        #plot = self.ui.topPlotWidget.plot(result['primary'].view(numpy.ndarray) / self.inpScale, x=result.xvals('Time'), params=params)
        plot = self.ui.topPlotWidget.plot(result['primary'].view(numpy.ndarray), x=result.xvals('Time'), params=params)
        
    def quit(self):
        TaskGui.quit(self)
        if not sip.isdeleted(self.daqUI):
            Qt.QObject.disconnect(self.daqUI, Qt.SIGNAL('changed'), self.daqChanged)
        self.ui.topPlotWidget.close()
        self.ui.bottomPlotWidget.close()
