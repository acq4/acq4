# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from ProtocolTemplate import *
from DaqChannelGui import *
from lib.devices.Device import ProtocolGui
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
from PyQt4 import Qwt5 as Qwt
import numpy

class DAQGenericProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        self.stateGroup = WidgetGroup([
            (self.ui.topSplitter, 'splitter1'),
            (self.ui.controlSplitter, 'splitter2'),
            (self.ui.plotSplitter, 'splitter3'),
        ])
        
        self.plots = {}
        self.channels = {}
        
        ## Create plots and control widgets
        for ch in self.dev.config:
            conf = self.dev.config[ch]
            p = Qwt.QwtPlot(self.ui.plotSplitter)
            self.plots[ch] = p
            
            if conf['type'] in ['ao', 'do']:
                w = OutputChannelGui(self.ui.controlSplitter, ch, conf, p, dev, prot)
            elif conf['type'] in ['ai', 'di']:
                w = InputChannelGui(self.ui.controlSplitter, ch, conf, p, dev, prot)
            else:
                raise Exception("Unrecognized device type '%s'" % conf['type'])
            self.channels[ch] = w
        
        

    def saveState(self):
        state = self.stateGroup.state().copy()
        state['channels'] = {}
        for ch in self.channels:
            state['channels'][ch] = self.channels[ch].saveState()

    def restoreState(self, state):
        try:
            self.stateGroup.setState(state)
            for ch in state['channels']:
                self.channels[ch].restoreState(state['channels'][ch])
        except:
            sys.excepthook(*sys.exc_info())
        #self.ui.waveGeneratorWidget.update()
            
        
    def listSequence(self):
        ## returns sequence parameter names and lengths
        l = []
        for ch in self.channels:
            l.extend(self.channels[ch].listSequence())
        return l
        
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        p = {}
        for ch in self.channels:
            p[ch] = self.channels[ch].generateProtocol(params)
        return p
        
    def handleResult(self, result):
        for ch in self.channels:
            self.channels[ch].handleResult(result[ch])
            
            