# -*- coding: utf-8 -*-
from ProtocolTemplate import Ui_Form
from lib.devices.Device import ProtocolGui
from PyQt4 import QtCore, QtGui

class ScannerProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)

    def saveState(self):
        pass
        
    def restoreState(self, state):
        pass
        
    def listSequence(self):
        pass
        
    def generateProtocol(self, params=None):
        pass
        
    def handleResult(self, result, params):
        pass