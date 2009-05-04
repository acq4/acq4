# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
from lib.util.WidgetGroup import *

class PVCamProto(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = WidgetGroup([
            (self.ui.recordCheck, 'record'),
            (self.ui.triggerCheck, 'trigger'),
            (self.ui.displayCheck, 'display'),
            (self.ui.recordExposeCheck, 'recordExposeChannel'),
            (self.ui.splitter, 'splitter')
        ])

    def saveState(self):
        s = self.currentState()
        return s
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        
        
    def generateProtocol(self, params={}):
        return self.currentState()
        
    def currentState(self):
        return self.stateGroup.state()
        
    def handleResult(self, result, dataManager):
        #print result
        if self.stateGroup.state()['display']:
            self.ui.imageView.setImage(result['frames'])
