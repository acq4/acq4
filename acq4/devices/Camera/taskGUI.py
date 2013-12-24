# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from TaskTemplate import *
from acq4.devices.DAQGeneric.taskGUI import DAQGenericTaskGui
from acq4.devices.Device import TaskGui
#from acq4.pyqtgraph.WidgetGroup import WidgetGroup
import numpy as np
import acq4.pyqtgraph as pg
#from acq4.pyqtgraph.graphicsItems import InfiniteLine, VTickGroup
#from PyQt4 import Qwt5 as Qwt

class CameraTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, task):
        DAQGenericTaskGui.__init__(self, dev, task, ownUi=False)  ## When initializing superclass, make sure it knows this class is creating the ui.
        
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.stateGroup = pg.WidgetGroup(self) ## create state group before DAQ creates its own interface
        self.ui.horizSplitter.setStretchFactor(0, 0)
        self.ui.horizSplitter.setStretchFactor(1, 1)
        
        DAQGenericTaskGui.createChannelWidgets(self, self.ui.ctrlSplitter, self.ui.plotSplitter)
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
            l = pg.InfiniteLine()
            self.vLines.append(l)
            self.plots['trigger'].addItem(self.vLines[0])
        if 'exposure' in self.plots:
            l = pg.InfiniteLine()
            self.vLines.append(l)
            self.plots['exposure'].addItem(self.vLines[1])
            
        self.frameTicks = pg.VTickGroup()
        self.frameTicks.setYRange([0.8, 1.0])
        
        #self.roiRect = QtGui.QGraphicsRectItem()
        #self.cameraModule = None
        
        #self.ui.exposePlot.registerPlot(self.dev.name + '.Expose')
        #self.ui.triggerPlot.registerPlot(self.dev.name + '.Trigger')
        #self.ui.imageView.ui.roiPlot.registerPlot(self.dev.name + '.ROI')
        
        #QtCore.QObject.connect(self.ui.recordExposeCheck, QtCore.SIGNAL('clicked()'), self.recordExposeClicked)
        #QtCore.QObject.connect(self.ui.imageView, QtCore.SIGNAL('timeChanged'), self.timeChanged)
        self.ui.imageView.sigTimeChanged.connect(self.timeChanged)
        
        #QtCore.QObject.connect(self.task, QtCore.SIGNAL('taskPaused'), self.taskPaused)
        self.task.sigTaskPaused.connect(self.taskPaused)
        #QtCore.QObject.connect(self.ui.imageView.ui.roiBtn, QtCore.SIGNAL('clicked'), self.connectROI)
        
        
    #def connectROI(self):
        #"""Display (or hide) the ImageView's ROI in the camera's module, if there is one"""
        
    #def updateROI(self):
        
        
            
    def timeChanged(self, i, t):
        for l in self.vLines:
            l.setValue(t)
        

    def saveState(self):
        s = self.currentState()
        s['daqState'] = DAQGenericTaskGui.saveState(self)
        return s
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        if 'daqState' in state:
            DAQGenericTaskGui.restoreState(self, state['daqState'])
        
        
    def generateTask(self, params=None):
        daqProt = DAQGenericTaskGui.generateTask(self, params)
        
        if params is None:
            params = {}
        state = self.currentState()
        task = {
            'record': state['recordCheck'],
            #'recordExposeChannel': state['recordExposeCheck'],
            'triggerProtocol': state['triggerCheck'],
            'params': {
                'triggerMode': state['triggerModeCombo']
            }
        }
        task['channels'] = daqProt
        if state['releaseBetweenRadio']:
            task['pushState'] = None
            task['popState'] = None
        return task
        
    def taskSequenceStarted(self):
        DAQGenericTaskGui.taskSequenceStarted(self)
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.pushState('cam_proto_state')
        
    def taskFinished(self):
        DAQGenericTaskGui.taskFinished(self)
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.popState('cam_proto_state')

    def taskPaused(self):  ## If the task is paused, return the camera to its previous state until we start again
        if self.ui.releaseAfterRadio.isChecked():
            self.dev.popState('cam_proto_state')
            self.dev.pushState('cam_proto_state')
        
        
    def currentState(self):
        return self.stateGroup.state()
        
    def handleResult(self, result, params):
        #print result
        state = self.stateGroup.state()
        if state['displayCheck']:
            if result is None or len(result.frames()) == 0:
                print "No images returned from camera task."
                self.ui.imageView.clear()
            else:
                self.ui.imageView.setImage(result.asMetaArray())
                #print "  frame times:", list(result['frames'].xvals('Time'))
                frameTimes, precise = result.frameTimes()
                if precise:
                    self.frameTicks.setXVals(frameTimes)
                
        DAQGenericTaskGui.handleResult(self, result.daqResult(), params)
        #if state['displayExposureCheck'] and 'expose' in result and result['expose'] is not None:
            #d = result['expose']
            #if self.exposeCurve is None:
                #self.exposeCurve = self.ui.exposePlot.plot(d.view(ndarray), x=d.xvals('Time'), pen=QtGui.QPen(QtGui.QColor(200, 200, 200)))
            #else:
                #self.exposeCurve.setData(y=d.view(ndarray), x=d.xvals('Time'))
                #self.ui.exposePlot.replot()


    #def recordExposeClicked(self):
        #daq = self.dev.config['exposeChannel'][0]
        #self.task.getDevice(daq)
        
    def quit(self):
        self.ui.imageView.close()
        DAQGenericTaskGui.quit(self)
        
