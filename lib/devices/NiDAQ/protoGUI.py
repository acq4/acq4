# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui

class NiDAQProto(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.nPts = 0
        self.updateNPts()
        self.updateDevList()
        self.devs = []
        QtCore.QObject.connect(self.ui.rateSpin, QtCore.SIGNAL('valueChanged(int)'), self.updateNPts)
        QtCore.QObject.connect(self.prot, QtCore.SIGNAL('durationChanged(float)'), self.updateNPts)
        
    def saveState(self):
        return self.currentState()
        
    def restoreState(self, state):
        self.ui.rateSpin.setValue(state['rate'])
        if 'triggerDevice' in state and state['triggerDevice'] in self.devs:
            self.ui.triggerDevList.setCurrentIndex(self.devs.index(state['triggerDevice'])+1)
        else:
            self.ui.triggerDevList.setCurrentIndex(0)
        
    def generateProtocol(self, params={}):
        return self.currentState()
        
    def currentState(self):
        state = {}
        state['rate'] = self.ui.rateSpin.value()
        self.updateNPts()
        state['numPts'] = self.nPts
        if self.ui.triggerDevList.currentIndex() > 0:
            state['triggerDevice'] = self.ui.triggerDevList.currentText()
        return state
        
    def updateNPts(self, *args):
        dur = self.prot.getParam('duration')
        nPts = dur * self.ui.rateSpin.value()
        if nPts != self.nPts:
            self.nPts = nPts
            self.ui.numPtsLabel.setText(str(self.nPts))
            self.emit(QtCore.SIGNAL('changed(PyQt_PyObject)'), self.currentState())
        
    def updateDevList(self):
        self.devs = self.dev.dm.listDevices()
        self.ui.triggerDevList.clear()
        self.ui.triggerDevList.addItem('No Trigger')
        for d in self.devs:
            self.ui.triggerDevList.addItem(d)
            