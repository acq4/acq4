# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from .TaskTemplate import *
from acq4.devices.DAQGeneric.taskGUI import DAQGenericTaskGui
from acq4.devices.Device import TaskGui
#from acq4.pyqtgraph.WidgetGroup import WidgetGroup
import numpy as np
import acq4.pyqtgraph as pg
#from acq4.pyqtgraph.graphicsItems import InfiniteLine, VTickGroup
#from acq4.util import Qt

class CameraTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner):
        DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)  ## When initializing superclass, make sure it knows this class is creating the ui.
        
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
        
        conf = self.dev.camConfig
            
        tModes = self.dev.listParams('triggerMode')[0]
        for m in tModes:
            item = self.ui.triggerModeCombo.addItem(m)
        
        self.vLines = []
        if 'trigger' in self.plots:
            l = pg.InfiniteLine()
            self.vLines.append(l)
            self.plots['trigger'].addItem(l)
        if 'exposure' in self.plots:
            l = pg.InfiniteLine()
            self.vLines.append(l)
            self.plots['exposure'].addItem(l)
            
        self.frameTicks = pg.VTickGroup()
        self.frameTicks.setYRange([0.8, 1.0])
        
        self.ui.imageView.sigTimeChanged.connect(self.timeChanged)
        
        self.taskRunner.sigTaskPaused.connect(self.taskPaused)
        
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
            # For now, the task gui only changes triggerMode. If we allow
            # other parameters to be changed from here, then they will have to be added
            # to the list of parameters to push/pop
            self.dev.pushState('cam_proto_state', params=['triggerMode'])
        
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
        state = self.stateGroup.state()
        if state['displayCheck']:
            if result is None or len(result.frames()) == 0:
                print("No images returned from camera task.")
                self.ui.imageView.clear()
            else:
                frameTimes, precise = result.frameTimes()
                if precise:
                    self.ui.imageView.setImage(result.asMetaArray(), xvals=frameTimes)
                    self.frameTicks.setXVals(frameTimes)
                else:
                    self.ui.imageView.setImage(result.asMetaArray())
                
        DAQGenericTaskGui.handleResult(self, result.daqResult(), params)
        
    def quit(self):
        self.ui.imageView.close()
        DAQGenericTaskGui.quit(self)
        
