# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui

class PVCamProto(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

    def saveState(self):
        return self.currentState()
        
    def restoreState(self, state):
        self.ui.recordCheck.setChecked(state['record'])
        self.ui.triggerCheck.setChecked(state['trigger'])
        self.ui.displayCheck.setChecked(state['display'])
        self.ui.recordExposeCheck.setChecked(state['recordExposeChannel'])
        
        
    def generateProtocol(self, params={}):
        return self.currentState()
        
    def currentState(self):
        state = {}
        state['record'] = self.ui.recordCheck.isChecked()
        state['trigger'] = self.ui.triggerCheck.isChecked()
        state['display'] = self.ui.displayCheck.isChecked()
        state['recordExposeChannel'] = self.ui.recordExposeCheck.isChecked()
        return state
