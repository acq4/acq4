# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
from lib.util.WidgetGroup import *
from numpy import ndarray
from PyQt4 import Qwt5 as Qwt

class PVCamProto(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = WidgetGroup(self)
        #self.stateGroup = WidgetGroup([
            #(self.ui.recordCheck, 'record'),
            #(self.ui.triggerCheck, 'trigger'),
            #(self.ui.displayCheck, 'display'),
            #(self.ui.recordExposeCheck, 'recordExposeChannel'),
            #(self.ui.splitter, 'splitter')
        #])
        
        conf = self.dev.config
        if 'exposeChannel' not in conf:
            self.ui.exposureGroupBox.hide()
        if 'triggerInChannel' not in conf:
            self.ui.triggerGroupBox.hide()
        if 'triggerOutChannel' not in conf:
            self.ui.triggerCheck.hide()
            
        tModes = self.dev.listTriggerModes().keys()
        tModes.remove('Normal')
        tModes = ['Normal'] + tModes
        for m in tModes:
            item = self.ui.triggerModeCombo.addItem(m)
            
        QtCore.QObject.connect(self.ui.recordExposeCheck, QtCore.SIGNAL('clicked()'), self.recordExposeClicked)
            

    def saveState(self):
        s = self.currentState()
        return s
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        
        
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        state = self.currentState()
        prot = {
            'record': state['recordCheck'],
            'recordExposeChannel': state['recordExposeCheck'],
            'triggerProtocol': state['triggerCheck'],
            'triggerMode': state['triggerModeCombo']
        }
        return prot
        
        
    def currentState(self):
        return self.stateGroup.state()
        
    def handleResult(self, result, params):
        #print result
        state = self.stateGroup.state()
        if state['displayCheck']:
            if result['frames'] is None:
                print "No images returned from camera protocol."
            else:
                self.ui.imageView.setImage(result['frames'])
                
        if state['displayExposureCheck'] and 'expose' in result and result['expose'] is not None:
            #self.ui.exposePlot.plotMetaArray(result['expose'])
            self.ui.exposePlot.clear()
            c = Qwt.QwtPlotCurve()
            d = result['expose']
            c.setData(d.xvals('Time'), d.view(ndarray))
            c.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            c.attach(self.ui.exposePlot)
            self.ui.exposePlot.plot()


    def recordExposeClicked(self):
        daq = self.dev.config['exposeChannel'][0]
        self.prot.getDevice(daq)