# -*- coding: utf-8 -*-
from lib.modules.ProtocolRunner.analysisModules import AnalysisModule
from lib.Manager import getManager
from PyQt4 import QtCore, QtGui
from imagingTemplate import Ui_Form
import numpy as np

class ImagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.postGuiInit()
        self.man = getManager()
        #devs = self.man.listDevices()
        #for d in devs:
            #self.ui.scannerDevCombo.addItem(d)
            #self.ui.clampDevCombo.addItem(d)
            
        #self.fillModuleList()
        self.ui.scannerComboBox.setTypes('scanner')
        self.ui.detectorComboBox.setTypes('daqChannelGroup')
                
    def quit(self):
        AnalysisModule.quit(self)
        
    def protocolStarted(self, *args):
        #print "start:",args
        #self.newProt()
        pass
    
    def protocolFinished(self):
        pass
        
    def newFrame(self, frame):
        pass

    def detectorDevice(self):
        return str(self.ui.detectorComboBox.currentText())
        
    def scannerDevice(self):
        return str(self.ui.scannerDevCombo.currentText())
        
        

        