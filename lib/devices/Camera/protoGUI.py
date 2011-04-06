# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from ProtocolTemplate import *
from lib.devices.DAQGeneric.protoGUI import DAQGenericProtoGui
from lib.devices.Device import ProtocolGui
from WidgetGroup import *
from numpy import ndarray
from pyqtgraph.graphicsItems import InfiniteLine, VTickGroup
#from PyQt4 import Qwt5 as Qwt

class CameraProtoGui(DAQGenericProtoGui):
    def __init__(self, dev, prot):
        DAQGenericProtoGui.__init__(self, dev, prot, ownUi=False)  ## When initializing superclass, make sure it knows this class is creating the ui.
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = WidgetGroup(self) ## create state group before DAQ creates its own interface
        self.ui.horizSplitter.setStretchFactor(0, 0)
        self.ui.horizSplitter.setStretchFactor(1, 1)
        
        DAQGenericProtoGui.createChannelWidgets(self, self.ui.ctrlSplitter, self.ui.plotSplitter)
        self.ui.plotSplitter.setStretchFactor(0, 10)
        self.ui.plotSplitter.setStretchFactor(1, 1)
        self.ui.plotSplitter.setStretchFactor(2, 1)
        
        ## plots should not be storing more than one trace at a time.
        for p in self.plots.values():
            p.plotItem.ctrl.maxTracesCheck.setChecked(True)
            p.plotItem.ctrl.maxTracesSpin.setValue(1)
            p.plotItem.ctrl.forgetTracesCheck.setChecked(True)
        
        #self.stateGroup = WidgetGroup([
            #(self.ui.recordCheck, 'record'),
            #(self.ui.triggerCheck, 'trigger'),
            #(self.ui.displayCheck, 'display'),
            #(self.ui.recordExposeCheck, 'recordExposeChannel'),
            #(self.ui.splitter, 'splitter')
        #])
        
        conf = self.dev.camConfig
        #if 'exposeChannel' not in conf:
            #self.ui.exposureGroupBox.hide()
        #if 'triggerInChannel' not in conf:
            #self.ui.triggerGroupBox.hide()
        #if 'triggerOutChannel' not in conf:
            #self.ui.triggerCheck.hide()
            
        #self.exposeCurve = None
            
        tModes = self.dev.listParams('triggerMode')[0]
        #tModes.remove('Normal')
        #tModes = ['Normal'] + tModes
        for m in tModes:
            item = self.ui.triggerModeCombo.addItem(m)
        
        self.vLines = []
        if 'trigger' in self.plots:
            l = InfiniteLine(self.plots['trigger'])
            self.vLines.append(l)
            self.plots['trigger'].addItem(self.vLines[0])
        if 'exposure' in self.plots:
            l = InfiniteLine(self.plots['exposure'])
            self.vLines.append(l)
            self.plots['exposure'].addItem(self.vLines[1])
            
        self.frameTicks = VTickGroup(view=self.ui.imageView.ui.roiPlot)
        self.frameTicks.setYRange([0.8, 1.0], relative=True)
        
        #self.roiRect = QtGui.QGraphicsRectItem()
        #self.cameraModule = None
        
        #self.ui.exposePlot.registerPlot(self.dev.name + '.Expose')
        #self.ui.triggerPlot.registerPlot(self.dev.name + '.Trigger')
        #self.ui.imageView.ui.roiPlot.registerPlot(self.dev.name + '.ROI')
        
        #QtCore.QObject.connect(self.ui.recordExposeCheck, QtCore.SIGNAL('clicked()'), self.recordExposeClicked)
        #QtCore.QObject.connect(self.ui.imageView, QtCore.SIGNAL('timeChanged'), self.timeChanged)
        self.ui.imageView.sigTimeChanged.connect(self.timeChanged)
        
        #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolPaused'), self.protocolPaused)
        self.prot.sigProtocolPaused.connect(self.protocolPaused)
        #QtCore.QObject.connect(self.ui.imageView.ui.roiBtn, QtCore.SIGNAL('clicked'), self.connectROI)
        
        
    #def connectROI(self):
        #"""Display (or hide) the ImageView's ROI in the camera's module, if there is one"""
        
    #def updateROI(self):
        
        
            
    def timeChanged(self, i, t):
        for l in self.vLines:
            l.setValue(t)
        

    def saveState(self):
        s = self.currentState()
        s['daqState'] = DAQGenericProtoGui.saveState(self)
        return s
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        DAQGenericProtoGui.restoreState(self, state['daqState'])
        
        
    def generateProtocol(self, params=None):
        daqProt = DAQGenericProtoGui.generateProtocol(self, params)
        
        if params is None:
            params = {}
        state = self.currentState()
        prot = {
            'record': state['recordCheck'],
            #'recordExposeChannel': state['recordExposeCheck'],
            'triggerProtocol': state['triggerCheck'],
            'params': {
                'triggerMode': state['triggerModeCombo']
            }
        }
        prot['channels'] = daqProt
        if state['releaseBetweenRadio']:
            prot['pushState'] = None
            prot['popState'] = None
        return prot
        
    def protocolStarted(self):
        DAQGenericProtoGui.protocolStarted(self)
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.pushState('cam_proto_state')
        
    def protocolFinished(self):
        DAQGenericProtoGui.protocolFinished(self)
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.popState('cam_proto_state')

    def protocolPaused(self):  ## If the protocol is paused, return the camera to its previous state until we start again
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.popState('cam_proto_state')
            self.dev.pushState('cam_proto_state')
        
        
    def currentState(self):
        return self.stateGroup.state()
        
    def handleResult(self, result, params):
        #print result
        state = self.stateGroup.state()
        if state['displayCheck']:
            if result is None or result['frames'] is None:
                print "No images returned from camera protocol."
            else:
                self.ui.imageView.setImage(result['frames'])
                #print "  frame times:", list(result['frames'].xvals('Time'))
                self.frameTicks.setXVals(result['frames'].xvals('Time'))
                
        DAQGenericProtoGui.handleResult(self, result['channels'], params)
        #if state['displayExposureCheck'] and 'expose' in result and result['expose'] is not None:
            #d = result['expose']
            #if self.exposeCurve is None:
                #self.exposeCurve = self.ui.exposePlot.plot(d.view(ndarray), x=d.xvals('Time'), pen=QtGui.QPen(QtGui.QColor(200, 200, 200)))
            #else:
                #self.exposeCurve.setData(y=d.view(ndarray), x=d.xvals('Time'))
                #self.ui.exposePlot.replot()


    #def recordExposeClicked(self):
        #daq = self.dev.config['exposeChannel'][0]
        #self.prot.getDevice(daq)
        
    def quit(self):
        self.ui.imageView.close()
        DAQGenericProtoGui.quit(self)
        