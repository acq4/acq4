# -*- coding: utf-8 -*-
from lib.modules.Module import *
from ProtocolRunnerTemplate import *
from PyQt4 import QtGui, QtCore
from lib.util.DirTreeModel import *
from lib.util.configfile import *

class ProtocolRunner(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.devListItems = {}
        self.docks = {}
        self.ui = Ui_MainWindow()
        self.win = QtGui.QMainWindow()
        self.ui.setupUi(self.win)
        
        self.protocolList = DirTreeModel(self.config['globalDir'])
        self.ui.protocolList.setModel(self.protocolList)
        
        self.currentProtocol = None   ## pointer to current protocol object
        
        #self.updateDeviceList()
        
        self.newProtocol()
        
        QtCore.QObject.connect(self.ui.newProtocolBtn, QtCore.SIGNAL('clicked()'), self.newProtocol)
        QtCore.QObject.connect(self.ui.saveProtocolBtn, QtCore.SIGNAL('clicked()'), self.saveProtocol)
        QtCore.QObject.connect(self.ui.loadProtocolBtn, QtCore.SIGNAL('clicked()'), self.loadProtocol)
        QtCore.QObject.connect(self.ui.saveAsProtocolBtn, QtCore.SIGNAL('clicked()'), self.saveProtocolAs)
        QtCore.QObject.connect(self.ui.deleteProtocolBtn, QtCore.SIGNAL('clicked()'), self.deleteProtocol)
        QtCore.QObject.connect(self.ui.testSingleBtn, QtCore.SIGNAL('clicked()'), self.testSingle)
        QtCore.QObject.connect(self.ui.runProtocolBtn, QtCore.SIGNAL('clicked()'), self.runSingle)
        QtCore.QObject.connect(self.ui.deviceList, QtCore.SIGNAL('itemChanged(QListWidgetItem*)'), self.deviceItemChanged)
        
        self.win.show()
        
        
    def updateDeviceList(self, protocol=None):
        """Read the list of devices from the device manager"""
        devList = self.manager.listDevices()
        
        if protocol is not None:
            protList = protocol.conf['devices'].keys()
        elif self.currentProtocol is not None:
            protList = self.currentProtocol.conf['devices'].keys()
        else:
            protList = []
            
        ## Remove all devices that do not exist and are not referenced by the protocol
        rem = []
        for d in self.devListItems:
            if d not in devList and d not in protList:
                self.ui.deviceList.takeItem(self.ui.deviceList.row(self.devListItems[d]))
                rem.append(d)
        for d in rem:
            del self.devListItems[d]
                
        ## Add all devices that exist in the current system
        for d in devList:
            if d not in self.devListItems:
                self.devListItems[d] = QtGui.QListWidgetItem(d, self.ui.deviceList)
            self.devListItems[d].setForeground(QtGui.QBrush(QtGui.QColor(0,0,0)))
            
            
        ## Add all devices that are referenced by the protocol but do not exist
        for d in protList:
            if d not in self.devListItems:
                self.devListItems[d] = QtGui.QListWidgetItem(d, self.ui.deviceList)
                self.devListItems[d].setForeground(QtGui.QBrush(QtGui.QColor(150,0,0)))
            
        ## Make sure flags and checkState are correct for all items
        for d in self.devListItems:
            self.devListItems[d].setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            if d in protList:
                self.devListItems[d].setCheckState(QtCore.Qt.Checked)
            else:
                self.devListItems[d].setCheckState(QtCore.Qt.Unchecked)
                
        
    def updateDocks(self, protocol = None):
        if protocol is None:
            protocol = self.currentProtocol
        
        ## (un)hide docks as needed
        for d in self.docks:
            if d not in protocol.enabledDevices():
                self.docks[d].hide()
            else:
                self.docks[d].show()
            
        ## Create docks that don't exist
        for d in protocol.enabledDevices():
            if d not in self.docks:
                if d not in self.manager.listDevices():
                    continue
                dev = self.manager.getDevice(d)
                dw = dev.protocolInterface()
                dock = QtGui.QDockWidget(d)
                dock.setFeatures(dock.AllDockWidgetFeatures)
                dock.setWidget(dw)
                
                self.docks[d] = dock
                self.win.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        
    def deviceItemChanged(self, item):
        if item.checkState() == QtCore.Qt.Unchecked:
            self.currentProtocol.removeDevice(str(item.text()))
        else:
            self.currentProtocol.addDevice(str(item.text()))
        self.updateDocks()
        
    def clearDocks(self):
        for d in self.docks:
            self.win.removeDockWidget(self.docks[d])
        self.docks = {}
        
    def closeProtocol(self):
        ## Remove all docks
        self.clearDocks()
        
        ## Clear sequence list
        self.ui.sequenceList.clearItems()
        
        
    def newProtocol(self):
        ## Remove all docks
        self.clearDocks()
        
        ## Create new empty protocol object
        self.currentProtocol = Protocol()
        
        ## Clear extra devices in dev list
        self.updateDeviceList()
        
        self.updateProtParams()
        
        ## Clear sequence parameters, disable sequence dock
    
    def updateProtParams(self, prot=None):
        if prot is None:
            prot = self.currentProtocol
        self.ui.protoDurationSpin.setValue(prot.conf['duration'])
        if prot.conf['continuous']:
            self.ui.protoContinuousCheck.setCheckState(QtCore.Qt.Checked)
        else:
            self.ui.protoContinuousCheck.setCheckState(QtCore.Qt.Unchecked)
    
    def loadProtocol(self):
        ## Determine selected item
        sel = list(self.ui.protocolList.selectedIndexes())
        if len(sel) == 1:
            sel = sel[0]
        else:
            raise Exception("Can not load--%d items selected" % len(sel))
            
        fn = self.protocolList.getFileName(sel)
        
        ## Create protocol object from requested file
        prot = Protocol(fileName=fn)
        
        ## Remove all docks
        self.clearDocks()
        
        ## Update protocol parameters
        self.updateProtParams(prot)
        
        ## update dev list
        self.updateDeviceList(prot)
        
        ## Update sequence parameters, dis/enable sequence dock
        
        ## Create new docks
        self.updateDocks(prot)
        
        ## Configure dock positions
        if 'winState' in prot.conf:
            self.win.restoreState(prot.conf['winState'])
            
        self.currentProtocol = prot
    
    def saveProtocol(self):
        ## Write protocol config to file
        
        pass
    
    def saveProtocolAs(self):
        ## Request new file name
        ## update file name in protocol
        ## Write protocol config to file
        ## update protocol list
        pass
    
    def deleteProtocol(self):
        
        pass
    
    def testSingle(self):
        self.runSingle(store=False)
    
    def runSingle(self, store=True):
        ## Generate executable conf from protocol object
        ## Send conf to devicemanager for execution
        ## Request each dock handle the results with/without storage
        prot = self.generateProtocol()
        result = self.manager.runProtocol(prot)
        self.handleResult(result)
   
    def testSequence(self):
        self.runSequence(store=False)
       
    def runSequence(self):
        pass
    
class Protocol:
    def __init__(self, fileName=None):
        
        if fileName is not None:
            self.name = os.path.split(fileName)[1]
            self.conf = readConfigFile(fileName)
            for d in self.conf['devices']:
                self.conf['devices'][d]['enabled'] = True
            #self.duration = self.conf['duration']
            #self.continuous = self.conf['continuous']
            #self.devList = self.conf['devices'].keys()
            #self.winState = self.conf['winState']
        else:
            self.name = ""
            #self.devList = []
            #self.duration = 1.0
            #self.continuous = False
            #self.winState = None
            self.conf = {'devices': {}, 'duration': 0.2, 'continuous': False}
        
    def generateProtocol(self, **args):
        """Generate the configuration data that will execute this protocol"""
        pass
    
    def write(self, fileName):
        pass
    
    def enabledDevices(self):
        return [i for i in self.conf['devices'] if self.conf['devices'][i]['enabled']]
        
    def removeDevice(self, dev):
        if dev in self.conf['devices']:
            self.conf['devices'][dev]['enabled'] = False
        
    def addDevice(self, dev):
        if dev not in self.conf['devices']:
            self.conf['devices'][dev] = {}
        self.conf['devices'][dev]['enabled'] = True