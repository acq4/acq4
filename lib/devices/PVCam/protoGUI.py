# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.Device import ProtocolGui
from lib.util.WidgetGroup import *
from lib.util.PlotWidget import PlotCurve
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
            
        self.exposeCurve = None
            
        tModes = self.dev.listTriggerModes().keys()
        tModes.remove('Normal')
        tModes = ['Normal'] + tModes
        for m in tModes:
            item = self.ui.triggerModeCombo.addItem(m)
        
        self.vLines = []
        for i in range(2):
            l = Qwt.QwtPlotMarker()
            self.vLines.append(l)
            l.setLineStyle(Qwt.QwtPlotMarker.VLine)
            l.setLinePen(QtGui.QPen(QtGui.QColor(255, 255, 0)))
            l.setXValue(0.0)
        self.vLines[0].attach(self.ui.exposePlot)
        self.vLines[1].attach(self.ui.triggerPlot)
        
        QtCore.QObject.connect(self.ui.recordExposeCheck, QtCore.SIGNAL('clicked()'), self.recordExposeClicked)
        QtCore.QObject.connect(self.ui.imageView, QtCore.SIGNAL('timeChanged'), self.timeChanged)
            
    def timeChanged(self, i, t):
        for l in self.vLines:
            l.setXValue(t)
        self.ui.exposePlot.replot()
        self.ui.triggerPlot.replot()
        

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
            #self.ui.exposePlot.clear()
            d = result['expose']
            if self.exposeCurve is None:
                self.exposeCurve = self.ui.exposePlot.plot(d.view(ndarray), x=d.xvals('Time'), pen=QtGui.QPen(QtGui.QColor(200, 200, 200)))
            else:
                self.exposeCurve.setData(y=d.view(ndarray), x=d.xvals('Time'))
                self.ui.exposePlot.replot()
            #c = PlotCurve()
            #c.setData(d.xvals('Time'), d.view(ndarray))
            #c.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            #c.attach(self.ui.exposePlot)
            #self.ui.exposePlot.replot()


    def recordExposeClicked(self):
        daq = self.dev.config['exposeChannel'][0]
        self.prot.getDevice(daq)