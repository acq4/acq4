# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from .TaskTemplate import *
from acq4.devices.Device import TaskGui
from acq4.util.debug import *
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
import sys


class NiDAQTask(TaskGui):
    
    sigChanged = Qt.Signal(object)
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.nPts = 0
        self.ignorePeriod = False
        self.ignoreRate = False
        self.rate = 40e3

        self._block_update = False # use to block signal emission during bulk updates

        self.updateNPts()
        self.updateDevList()
        self.ui.rateSpin.setOpts(dec=True, step=0.5, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        self.ui.periodSpin.setOpts(dec=True, step=0.5, minStep=1e-6, bounds=[1e-6,None], siPrefix=True, suffix='s')
        self.ui.besselCutoffSpin.setOpts(value=20e3, dec=True, step=0.5, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        self.ui.butterworthPassbandSpin.setOpts(value=20e3, dec=True, step=0.5, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        self.ui.butterworthStopbandSpin.setOpts(value=40e3, dec=True, step=0.5, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        
        ## important to create widget group before connecting anything else.
        self.stateGroup = WidgetGroup([
            (self.ui.rateSpin, 'rate'),
            (self.ui.downsampleSpin, 'downsample'),
            (self.ui.triggerDevList, 'triggerDevice'),
            (self.ui.denoiseCombo, 'denoiseMethod'),
            (self.ui.denoiseThresholdSpin, 'denoiseThreshold'),
            (self.ui.denoiseWidthSpin, 'denoiseWidth'),
            (self.ui.filterCombo, 'filterMethod'),
            (self.ui.besselCutoffSpin, 'besselCutoff'),
            (self.ui.besselOrderSpin, 'besselOrder'),
            (self.ui.besselBidirCheck, 'besselBidirectional'),
            (self.ui.butterworthPassbandSpin, 'butterworthPassband'),
            (self.ui.butterworthStopbandSpin, 'butterworthStopband'),
            (self.ui.butterworthPassDBSpin, 'butterworthPassDB'),
            (self.ui.butterworthStopDBSpin, 'butterworthStopDB'),
            (self.ui.butterworthBidirCheck, 'butterworthBidirectional'),
        ])
        
        self.ui.periodSpin.sigValueChanging.connect(self.updateRateSpin)
        self.ui.rateSpin.sigValueChanging.connect(self.updatePeriodSpin)
        self.taskRunner.sigTaskChanged.connect(self.taskChanged)
        self.ui.denoiseCombo.currentIndexChanged.connect(self.updateDenoiseCtrl)
        self.ui.filterCombo.currentIndexChanged.connect(self.updateFilterCtrl)
        self.ui.rateSpin.setValue(self.rate)
        self.stateGroup.sigChanged.connect(self.stateChanged)

        self.updateDenoiseCtrl()
        self.updateFilterCtrl()
        
    def quit(self):
        self.taskRunner.sigTaskChanged.disconnect(self.taskChanged)
        TaskGui.quit(self)
        
    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        block = self._block_update
        try:
            self._block_update = True
            self.stateGroup.setState(state)
        except Exception:
            printExc("Error while loading DAQ task GUI configuration (proceeding with default configuration) :")
        finally:
            self._block_update = block
            self.stateChanged()
        
    def generateTask(self, params=None):
        task = self.currentState()
        task2 = {}
        
        # just for cleanliness, remove any filtering parameters that are not in use:
        remNames = ['butterworth', 'bessel']
        if task['filterMethod'].lower() in remNames:
            remNames.remove(task['filterMethod'].lower())
        if task['denoiseMethod'] == 'None':
            remNames.append('denoiseWidth')
            remNames.append('denoiseThreshold')
        for k in task:
            if not any(map(k.startswith, remNames)):
                task2[k] = task[k]
        
        return task2
        
    def currentState(self):
        self.updateNPts()
        state = self.stateGroup.state()
        ## make sure all of these are up to date:
        state['numPts'] = self.nPts
        state['rate'] = self.rate
        state['downsample'] = self.ui.downsampleSpin.value()
        if self.ui.triggerDevList.currentIndex() > 0:
            state['triggerDevice'] = str(self.ui.triggerDevList.currentText())
        else:
            del state['triggerDevice']
        
        return state
        
    def updatePeriodSpin(self):
        if self.ignoreRate:
            return
        period = 1. / self.ui.rateSpin.value()
        
        self.ignorePeriod = True
        self.ui.periodSpin.setValue(period)
        self.ignorePeriod = False
        
    def updateRateSpin(self):
        if self.ignorePeriod:
            return
        period = self.ui.periodSpin.value()
        rate = 1.0 / period
        self.ignoreRate = True
        self.ui.rateSpin.setValue(rate)
        self.ignoreRate = False
        
    def stateChanged(self, name=None, val=None):
        if name == 'rate':
            self.rate = self.ui.rateSpin.value()
            self.updateNPts()
            
        if self._block_update:
            return
        state = self.currentState()
        self.sigChanged.emit(state)
        
    def taskChanged(self, n, v):
        if n == 'duration':
            self.updateNPts()
            self.sigChanged.emit(self.currentState())
        
    def updateNPts(self):
        dur = self.taskRunner.getParam('duration')
        nPts = int(dur * self.rate)
        if nPts != self.nPts:
            self.nPts = nPts
            self.ui.numPtsLabel.setText(str(self.nPts))
        
    def updateDevList(self):
        ## list all devices
        allDevNames = self.dev.dm.listDevices()
        ## convert device names into device handles
        allDevs = [self.dev.dm.getDevice(d) for d in allDevNames]
        ## select out devices which have trigger channel to this DAQ
        self.devs = [d.name() for d in allDevs if d.getTriggerChannel(self.dev.name()) is not None]
            
        self.ui.triggerDevList.clear()
        self.ui.triggerDevList.addItem('No Trigger')
        
        for d in self.devs:
            self.ui.triggerDevList.addItem(d)
            
    def updateDenoiseCtrl(self):
        denoise = self.ui.denoiseCombo.currentText()
        if denoise == 'None':
            self.ui.denoiseCtrl.hide()
        else:
            self.ui.denoiseCtrl.show()

    def updateFilterCtrl(self):
        filter = self.ui.filterCombo.currentText()
        if filter == 'None':
            self.ui.besselCtrl.hide()
            self.ui.butterworthCtrl.hide()
        elif filter == 'Bessel':
            self.ui.besselCtrl.show()
            self.ui.butterworthCtrl.hide()
        elif filter == 'Butterworth':
            self.ui.besselCtrl.hide()
            self.ui.butterworthCtrl.show()

