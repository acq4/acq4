# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
import sys

class NiDAQProto(ProtocolGui):
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
        QtCore.QObject.connect(self.ui.rateSpin, QtCore.SIGNAL('valueChanged(double)'), self.rateChanged)
        QtCore.QObject.connect(self.ui.periodSpin, QtCore.SIGNAL('valueChanged(double)'), self.periodChanged)
        QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolChanged'), self.protocolChanged)
        
    def quit(self):
        ProtocolGui.quit(self)
        QtCore.QObject.disconnect(self.prot, QtCore.SIGNAL('protocolChanged'), self.protocolChanged)
        
    def saveState(self):
        return self.currentState()
        
    def restoreState(self, state):
        try:
            if 'downsample' in state:
                self.ui.downsampleSpin.setValue(state['downsample'])
            self.ui.rateSpin.setValue(state['rate'] / 1000.)
            #print "trigger dev:", state['triggerDevice']
            #print self.devs
            if 'triggerDevice' in state and state['triggerDevice'] in self.devs:
                self.ui.triggerDevList.setCurrentIndex(self.devs.index(state['triggerDevice'])+1)
                #print "Set index to", self.devs.index(state['triggerDevice'])+1
            else:
                self.ui.triggerDevList.setCurrentIndex(0)
                #print "No index"
        except:
            sys.excepthook(*sys.exc_info())
            print "Error while loading DAQ configuration, proceeding with default configuration."
        
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        return self.currentState()
        
    def currentState(self):
        state = {}
        state['rate'] = self.ui.rateSpin.value() * 1e3
        self.updateNPts()
        state['numPts'] = self.nPts
        if self.ui.triggerDevList.currentIndex() > 0:
            state['triggerDevice'] = str(self.ui.triggerDevList.currentText())
        state['downsample'] = self.ui.downsampleSpin.value()
        return state
        
    def rateChanged(self):
        if self.ignoreRate:
            return
        self.rate = self.ui.rateSpin.value() * 1000.
        period = 1e6 / self.rate
        #self.ui.periodSpin.blockSignals(True)
        self.ignorePeriod = True
        self.ui.periodSpin.setValue(period)
        self.ignorePeriod = False
        #self.ui.periodSpin.blockSignals(False)
        self.updateNPts()
        self.emit(QtCore.SIGNAL('changed'), self.currentState())
        
    def periodChanged(self):
        if self.ignorePeriod:
            return
        period = self.ui.periodSpin.value()
        self.rate = 1e6 / period
        #self.ui.rateSpin.blockSignals(True)
        self.ignoreRate = True
        self.ui.rateSpin.setValue(self.rate / 1000.)
        self.ignoreRate = False
        #self.ui.rateSpin.blockSignals(False)
        self.updateNPts()
        self.emit(QtCore.SIGNAL('changed'), self.currentState())
        
    def protocolChanged(self, n, v):
        #print "caught protocol change", n, v
        if n == 'duration':
            self.updateNPts()
        self.emit(QtCore.SIGNAL('changed'), self.currentState())
        
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
            