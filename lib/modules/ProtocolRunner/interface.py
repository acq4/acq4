# -*- coding: utf-8 -*-
from lib.modules.Module import *
from ProtocolRunnerTemplate import *
from PyQt4 import QtGui, QtCore
from lib.util.DirTreeModel import *

class ProtocolRunner(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = Ui_MainWindow()
        self.win = QtGui.QMainWindow()
        self.ui.setupUi(self.win)
        
        self.protocolList = DirTreeModel(self.config['globalDir'])
        self.devList = {} ## Devices which currently exist in the system or the current protocol.
            ## The values are tuples: (Device is enabled in protocol, device is available for use)
        
        self.currentProtocol = None   ## pointer to current protocol object
        
        self.devListItems = {}
        self.updateDeviceList()
        
        QtCore.QObject.connect(self.ui.newProtocolBtn, QtCore.SIGNAL('clicked()'), self.newProtocol)
        QtCore.QObject.connect(self.ui.saveProtocolBtn, QtCore.SIGNAL('clicked()'), self.saveProtocol)
        QtCore.QObject.connect(self.ui.loadProtocolBtn, QtCore.SIGNAL('clicked()'), self.loadProtocol)
        QtCore.QObject.connect(self.ui.saveAsProtocolBtn, QtCore.SIGNAL('clicked()'), self.saveProtocolAs)
        QtCore.QObject.connect(self.ui.deleteProtocolBtn, QtCore.SIGNAL('clicked()'), self.deleteProtocol)
        QtCore.QObject.connect(self.ui.testSingleBtn, QtCore.SIGNAL('clicked()'), self.testSingle)
        QtCore.QObject.connect(self.ui.runProtocolBtn, QtCore.SIGNAL('clicked()'), self.runSingle)
        self.win.show()
        
        
    def updateDeviceList(self):
        """Read the list of devices from the device manager"""
        devList = self.manager.listDevices()
        protList = []
        if self.currentProtocol is not None:
            protList = self.currentProtocol.devices
            
        ## Remove all devices that do not exist and are not referenced by the protocol
        for d in devListItems:
            if d not in devList and d not in protList:
                self.ui.takeItem(self.ui.row(self.devListItems[d]))
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
        
    def updateDocks(self):
        self.docks = {}
        for d in self.devices:
            dw = self.devices[d].deviceInterface()
            dock = QtGui.QDockWidget(d)
            dock.setFeatures(dock.AllDockWidgetFeatures)
            dock.setWidget(dw)
            
            self.devRackDocks[d] = dock
            self.devRack.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        
    def clearDocks(self):
        pass
        
    def newProtocol(self, protocol):
        ## Remove all docks
        ## Clear extra devices in dev list
        ## Clear sequence parameters, disable sequence dock
        ## Create new empty protocol object
        pass
    
    def loadProtocol(self, protocol):
        ## Create protocol object from requested file
        ## Remove all docks
        ## Update dev list
        ## Update sequence parameters, dis/enable sequence dock
        ## Create new docks
        ## Configure dock positions
        
        
        pass
    
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
        self.name = ""
        self.devList = []
        self.duration = 1.0
        self.continuous = False
        self.protocol = {}
        
    def generateProtocol(self, **args):
        """Generate the configuration data that will execute this protocol"""
        pass
    
    def write(self, fileName):
        pass
    
    
#class DeviceListModel(QtCore.QAbstractListModel):
    #def __init__(self, pr, parent=None):
        #QtCore.QAbstractListModel.__init__(self, parent)
        #self.pr = pr
        #self.manager = pr.manager
        #self.updateDeviceList()
        
        
    #def rowCount(self, )
        #return len(self.fullDevList())
        
    #def data(self, index, role):
        #d = self.fullDevList()[index.row()]
        #if role == QtCore.Qt.DisplayRole:
            #return QtCore.QVariant(d)
        #elif role == QtCore.Qt.TextColorRole:
            #if d in self.devices:
                #return QtGui.QColor(0,0,0)
            #else:
                #return QtGui.QColor(150,0,0)
    
    #def headerData(self):
        #return QtCore.QVariant('Devices')
        
    #def flags(self):
        #return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable