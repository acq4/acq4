#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Summary
-------

Device interface to PMT Controller
"""
from __future__ import with_statement
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask, DAQGenericTaskGui
# from acq4.devices.PMTController import PMTController as PMTDevice
from acq4.util.Mutex import Mutex
from PyQt4 import QtCore, QtGui
import time
import numpy as np
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
from acq4.util.debug import printExc
from devGuiTemplate import *


class PMTController(DAQGeneric):
    """ PMTController provides control of the PMTs and monitoring of the PMTs as a device.
    """

    sigShowModeDialog = QtCore.Signal(object)
    sigHideModeDialog = QtCore.Signal()

    def __init__(self, dm, config, name):

        # Generate config to use for DAQ
        daqConfig = {}

        for ch in ['PMT0', 'PMT1']:
            if ch not in config:
                continue
            daqConfig[ch] = config[ch].copy()
            if daqConfig[ch].get('type', None) != 'ai':
                raise Exception("PMTController: Monitoring signals must have type:'ai'")


        self.config = config
        self.modeLock = Mutex(Mutex.Recursive)  # protects self.mdCanceled
        self.devLock = Mutex(Mutex.Recursive)  # protects self.holding, possibly self.config, ..others, perhaps?
        self.mdCanceled = False

        DAQGeneric.__init__(self, dm, daqConfig, name)

        dm.declareInterface(name, ['PMTController'], self)

    def createTask(self, cmd, parentTask):
        return PMTControllerTask(self, cmd, parentTask)

    def taskInterface(self, taskRunner):
        return PMTControllerTaskGui(self, taskRunner)

    def deviceInterface(self, win):
        return PMTControllerDevGui(self)
        
        
    def showModeDialog(self, msg):
        with self.modeLock:
            self.mdCanceled = False
        self.modeDialog.setText(msg)
        self.modeDialog.show()
        self.modeDialog.activateWindow()
        
    def hideModeDialog(self):
        self.modeDialog.hide()
        
    def modeDialogCanceled(self):
        with self.modeLock:
            return self.mdCanceled
        
    def modeDialogClicked(self):
        ## called when user clicks 'cancel' on the mode dialog
        self.mdCanceled = True
        self.modeDialog.hide()
        
    def getMode(self):
        #print "getMode"
        with self.devLock:
            #print "  got lock"
            global mode_tel, modeNames
            m = self.readChannel('ModeChannel', raw=True)
            #print "  read value"
            if m is None:
                return None
            mode = modeNames[np.argmin(np.abs(mode_tel-m))]
            return mode

class PMTControllerGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.npmt = self.dev.getNumberofPMTs()
        # show the PMT types in the device gui
        pmtID0 = self.dev.getPMTID(pmt=0)
        self.ui.PMT1_type.setText(pmtID0)
        pmtID1 = self.dev.getPMTID(pmt=1)
        self.ui.PMT2_type.setText(pmtID1)
        self.updateStatus()
        self.ui.PMT1_Reset.clicked.connect(self.reset1)        
        self.ui.PMT2_Reset.clicked.connect(self.reset2)

    def updateStatus(self):
        """ Display the PMT anode voltages in the GUI
        """
        v0 = self.dev.getPMTAnodeV(pmt=0)
        self.ui.PMT1_V.setValue(v0)
        v1 = self.dev.getPMTAnodeV(pmt=1)
        self.ui.PMT1_V.setValue(v1)

    def reset1(self):
        """ Reset PMT1 (reapply HV)
        """
        self.dev.resetPMT(pmt=0)

    def reset2(self):
        """ Reset PMT2 (reapply HV)
        """
        self.dev.resetPMT(pmt=1)
    

class PMTControllerTask(DAQGenericTask):
    """ Add the PMTs to the task, so that monitored information can be saved with the 
    data collected form the trial. This would be which PMTs were used for which channels,
    and the control voltages given to the PMTs to set thier anode voltage (HV). Note: we
    don't actually know what the HV is; we only know the control voltage. 

    """
    def __init__(self, dev, cmd, parentTask):
        # make a few changes for compatibility with multiclamp        
        if 'daqProtocol' not in cmd:
            cmd['daqProtocol'] = {}
        if 'command' in cmd:
            if 'holding' in cmd:
                cmd['daqProtocol']['command'] = {'command': cmd['command'], 'holding': cmd['holding']}
            else:
                cmd['daqProtocol']['command'] = {'command': cmd['command']}
    
        ## Make sure we're recording from the correct secondary channel

        cmd['daqProtocol']['primary'] = {'record': True}
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'], parentTask)
        self.cmd = cmd

    def configure(self):
        #   Record initial state or set initial value
        self.pmtState = self.dev.getPMTStatusDict()

        #  Do not configure daq until mode is set. Otherwise, holding values may be incorrect.
        DAQGenericTask.configure(self)
        
    def storeResult(self, dirHandle):
        #  DAQGenericTask.storeResult(self, dirHandle)
        #  dirHandle.setInfo(self.ampState)
        result = self.getResult()
        result._info[-1]['PMTState'] = self.pmtState
        dirHandle.writeFile(result, self.dev.name())


class PMTControllerTaskGui(DAQGenericTaskGui):
    def __init__(self, dev, taskRunner):
        DAQGenericTaskGui.__init__(self, dev, taskRunner, ownUi=False)

        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.splitter1 = QtGui.QSplitter()
        self.splitter1.setOrientation(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter1)

        self.splitter2 = QtGui.QSplitter()
        self.splitter2.setOrientation(QtCore.Qt.Vertical)
        self.modeCombo = QtGui.QComboBox()
        self.splitter2.addWidget(self.modeCombo)
        self.modeCombo.addItems(self.dev.listModes())

        self.splitter3 = QtGui.QSplitter()
        self.splitter3.setOrientation(QtCore.Qt.Vertical)

        (w1, p1) = self.createChannelWidget('primary')
        (w2, p2) = self.createChannelWidget('command')

        self.cmdWidget = w2
        self.inputWidget = w1
        self.cmdPlot = p2
        self.inputPlot = p1

        #  self.ctrlWidget = QtGui.QWidget()
        #  self.ctrl = Ui_protoCtrl()
        #  self.ctrl.setupUi(self.ctrlWidget)
        #  self.splitter2.addWidget(self.ctrlWidget)
        
        self.splitter1.addWidget(self.splitter2)
        self.splitter1.addWidget(self.splitter3)
        self.splitter2.addWidget(w1)
        self.splitter2.addWidget(w2)
        self.splitter3.addWidget(p1)
        self.splitter3.addWidget(p2)
        self.splitter1.setSizes([100, 500])
        
        self.stateGroup = WidgetGroup([
            (self.splitter1, 'splitter1'),
            (self.splitter2, 'splitter2'),
            (self.splitter3, 'splitter3'),
        ])
        
        self.modeCombo.currentIndexChanged.connect(self.modeChanged)
        self.modeChanged()
        
    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        state = {}
        state['daqState'] = DAQGenericTaskGui.saveState(self)
        state['mode'] = self.getMode()
        #state['holdingEnabled'] = self.ctrl.holdingCheck.isChecked()
        #state['holding'] = self.ctrl.holdingSpin.value()
        return state
        
    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        self.modeCombo.setCurrentIndex(self.modeCombo.findText(state['mode']))
        #self.ctrl.holdingCheck.setChecked(state['holdingEnabled'])
        #if state['holdingEnabled']:
        #    self.ctrl.holdingSpin.setValue(state['holding'])
        return DAQGenericTaskGui.restoreState(self, state['daqState'])
    
    def generateTask(self, params=None):
        daqTask = DAQGenericTaskGui.generateTask(self, params)
        
        task = {
            'mode': self.getMode(),
            'daqProtocol': daqTask
        }
        return task


class CancelException(Exception):
    pass
