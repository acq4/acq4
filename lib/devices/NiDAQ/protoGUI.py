# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
from debug import *
from pyqtgraph.WidgetGroup import WidgetGroup
import sys

class NiDAQProto(ProtocolGui):
    
    sigChanged = QtCore.Signal(object)
    
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.nPts = 0
        self.ignorePeriod = False
        self.ignoreRate = False
        self.rate = 40e3
        self.updateNPts()
        self.updateDevList()
        #self.devs = []
        self.ui.rateSpin.setOpts(dec=True, step=1, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        self.ui.periodSpin.setOpts(dec=True, step=1, minStep=1e-6, bounds=[1e-6,None], siPrefix=True, suffix='s')
        
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
            (self.ui.butterworthPassbandSpin, 'butterworthPassband'),
            (self.ui.butterworthStopbandSpin, 'butterworthStopband'),
            (self.ui.butterworthPassDBSpin, 'butterworthPassDB'),
            (self.ui.butterworthStopDBSpin, 'butterworthStopDB'),
        ])
        
        #QtCore.QObject.connect(self.ui.rateSpin, QtCore.SIGNAL('valueChanged(double)'), self.rateChanged)
        self.ui.rateSpin.valueChanged.connect(self.rateChanged)
        #QtCore.QObject.connect(self.ui.periodSpin, QtCore.SIGNAL('valueChanging'), self.updateRateSpin)
        self.ui.periodSpin.sigValueChanging.connect(self.updateRateSpin)
        #QtCore.QObject.connect(self.ui.rateSpin, QtCore.SIGNAL('valueChanging'), self.updatePeriodSpin)
        self.ui.rateSpin.sigValueChanging.connect(self.updatePeriodSpin)
        #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolChanged'), self.protocolChanged)
        self.prot.sigProtocolChanged.connect(self.protocolChanged)
        #QtCore.QObject.connect(self.ui.filterCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.ui.filterStack.setCurrentIndex)
        self.ui.filterCombo.currentIndexChanged.connect(self.ui.filterStack.setCurrentIndex)
        self.ui.rateSpin.setValue(self.rate)
        
        
    def quit(self):
        ProtocolGui.quit(self)
        QtCore.QObject.disconnect(self.prot, QtCore.SIGNAL('protocolChanged'), self.protocolChanged)
        
    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        
        try:
            #if 'rate' in state:
                #if 'downsample' in state:
                    #self.ui.downsampleSpin.setValue(state['downsample'])
                #self.ui.rateSpin.setValue(state['rate'] / 1000.)
                ##print "trigger dev:", state['triggerDevice']
                ##print self.devs
                #if 'triggerDevice' in state and state['triggerDevice'] in self.devs:
                    #self.ui.triggerDevList.setCurrentIndex(self.devs.index(state['triggerDevice'])+1)
                    ##print "Set index to", self.devs.index(state['triggerDevice'])+1
                #else:
                    #self.ui.triggerDevList.setCurrentIndex(0)
                    ##print "No index"
            #else:
            self.stateGroup.setState(state)
        except:
            #sys.excepthook(*sys.exc_info())
            printExc("Error while loading DAQ protocol GUI configuration (proceeding with default configuration) :")
        
    def generateProtocol(self, params=None):
        return self.currentState()
        
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
        
    def  updatePeriodSpin(self):
        if self.ignoreRate:
            return
        #self.rate = self.ui.rateSpin.value() * 1000.
        #period = 1e6 / self.rate
        period = 1. / self.ui.rateSpin.value()
        
        self.ignorePeriod = True
        self.ui.periodSpin.setValue(period)
        self.ignorePeriod = False
        
    def updateRateSpin(self):
        if self.ignorePeriod:
            return
        period = self.ui.periodSpin.value()
        #self.rate = 1e6 / period
        rate = 1.0 / period
        self.ignoreRate = True
        #self.ui.rateSpin.setValue(self.rate / 1000.)
        self.ui.rateSpin.setValue(rate)
        self.ignoreRate = False
        
    def rateChanged(self):
        self.rate = self.ui.rateSpin.value()
        self.updateNPts()
        #self.emit(QtCore.SIGNAL('changed'), self.currentState())
        self.sigChanged.emit(self.currentState())
        
        
    def protocolChanged(self, n, v):
        #print "caught protocol change", n, v
        if n == 'duration':
            self.updateNPts()
            #self.emit(QtCore.SIGNAL('changed'), self.currentState())
            self.sigChanged.emit(self.currentState())
        
    def updateNPts(self):
        dur = self.prot.getParam('duration')
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
        self.devs = [d.name for d in allDevs if d.getTriggerChannel(self.dev.name) is not None]
            
            
        self.ui.triggerDevList.clear()
        self.ui.triggerDevList.addItem('No Trigger')
        
        for d in self.devs:
            #print d, self.dev.name
            #dev = self.dev.dm.getDevice(d)
            #if dev.getTriggerChannel(self.dev.name) is not None:
                #print "------"
            self.ui.triggerDevList.addItem(d)
        #for p in self.dev.listTriggerPorts():
            #self.ui.triggerDevList.addItem(p)
        ## Add list of triggerable port names here?
            
