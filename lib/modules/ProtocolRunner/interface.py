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
        self.deleteState = 0
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
        QtCore.QObject.connect(self.ui.deviceList, QtCore.SIGNAL('itemClicked(QListWidgetItem*)'), self.deviceItemChanged)
        QtCore.QObject.connect(self.ui.protoDurationSpin, QtCore.SIGNAL('editingFinished()'), self.protParamsChanged)
        QtCore.QObject.connect(self.ui.protocolList, QtCore.SIGNAL('doubleClicked(const QModelIndex &)'), self.loadProtocol)
        QtCore.QObject.connect(self.ui.protocolList, QtCore.SIGNAL('clicked(const QModelIndex &)'), self.protoListClicked)
        QtCore.QObject.connect(self.protocolList, QtCore.SIGNAL('fileRenamed(PyQt_PyObject, PyQt_PyObject)'), self.fileRenamed)
        
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
                print "    ", d
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
                
    def protoListClicked(self, ind):
        ## Check to see if the selection has changed
        sel = list(self.ui.protocolList.selectedIndexes())
        if len(sel) == 1:
            self.ui.deleteProtocolBtn.setEnabled(True)
        else:
            self.ui.deleteProtocolBtn.setEnabled(False)
        self.resetDeleteState()
            
    def fileRenamed(self, fn1, fn2):
        ## A file was renamed, we might need to act on this change..
        if fn1 == self.currentProtocol.fileName:
            self.currentProtocol.fileName = fn2
            pn = fn2.replace(self.protocolList.baseDir, '')
            self.ui.currentProtocolLabel.setText(pn)
            return
        if os.path.isdir(fn2) and fn1 in self.currentProtocol.fileName:
            self.currentProtocol.fileName = self.currentProtocol.fileName.replace(fn1, fn2)
            pn = self.currentProtocol.fileName.replace(self.protocolList.baseDir, '')
            self.ui.currentProtocolLabel.setText(pn)
            return
            
        
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
                dock.setObjectName(d)
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
        
    def protParamsChanged(self):
        self.currentProtocol.conf['duration'] = self.ui.protoDurationSpin.value()
        self.currentProtocol.conf['continuous'] = self.ui.protoContinuousCheck.isChecked()
        #self.currentIsModified(True)
        
    #def currentIsModified(self, v):
        ### Inform the module whether the current protocol is modified from its stored state
        #self.currentProtocol.modified = v
        #if (not v) or (self.currentProtocol.fileName is not None):
            #self.ui.saveProtocolBtn.setEnabled(v)
        
    def newProtocol(self):
        ## Remove all docks
        self.clearDocks()
        
        ## Create new empty protocol object
        self.currentProtocol = Protocol()
        
        ## Clear extra devices in dev list
        self.updateDeviceList()
        
        self.updateProtParams()
        
        ## Clear sequence parameters, disable sequence dock
        
        self.ui.currentProtocolLabel.setText('[ new ]')
        
        self.ui.saveProtocolBtn.setEnabled(False)
        #self.currentIsModified(False)
    
    def updateProtParams(self, prot=None):
        if prot is None:
            prot = self.currentProtocol
        self.ui.protoDurationSpin.setValue(prot.conf['duration'])
        if prot.conf['continuous']:
            self.ui.protoContinuousCheck.setCheckState(QtCore.Qt.Checked)
        else:
            self.ui.protoContinuousCheck.setCheckState(QtCore.Qt.Unchecked)
    
    def getSelectedFileName(self):
        sel = list(self.ui.protocolList.selectedIndexes())
        if len(sel) == 1:
            index = sel[0]
        else:
            raise Exception("Can not load--%d items selected" % len(sel))
        return self.protocolList.getFileName(index)
    
    def loadProtocol(self, index=None):
        ## Determine selected item
        if index is None:
            sel = list(self.ui.protocolList.selectedIndexes())
            if len(sel) == 1:
                index = sel[0]
            else:
                raise Exception("Can not load--%d items selected" % len(sel))
            
        fn = self.protocolList.getFileName(index)
        
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
            self.win.restoreState(QtCore.QByteArray.fromPercentEncoding(prot.conf['winState']))
            
        pn = fn.replace(self.protocolList.baseDir, '')
        self.ui.currentProtocolLabel.setText(pn)
        self.currentProtocol = prot
        self.ui.saveProtocolBtn.setEnabled(True)
        #self.currentIsModified(False)
    
    def saveProtocol(self, fileName=None):
        ## store window state
        ws = str(self.win.saveState().toPercentEncoding())
        self.currentProtocol.conf['winState'] = ws
        
        ## Write protocol config to file
        self.currentProtocol.write(fileName)
        #self.currentIsModified(False)
        
        ## refresh protocol list
        self.protocolList.clearCache()
    
    def saveProtocolAs(self):
        ## Decide on new file name
        if self.currentProtocol.fileName is not None:
            baseFile = self.currentProtocol.fileName
        else:
            baseFile = os.path.join(self.protocolList.baseDir, 'protocol')
            
        c = 2
        newFile = None
        while True:
            newFile = baseFile + '_%02d' % c
            if not os.path.exists(newFile):
                break
            c += 1
            
        ## write
        self.saveProtocol(newFile)
        
        
        ## Start editing new file name
        index = self.protocolList.findIndex(newFile)
        #self.ui.protocolList.update(index)
        self.ui.protocolList.edit(index)
        
        pn = newFile.replace(self.protocolList.baseDir, '')
        self.ui.currentProtocolLabel.setText(pn)
        self.ui.saveProtocolBtn.setEnabled(True)
        #self.currentIsModified(False)
    
    def deleteProtocol(self):
        if self.deleteState == 0:
            self.ui.deleteProtocolBtn.setText('Really?')
            self.deleteState = 1
        elif self.deleteState == 1:
            try:
                fn = self.getSelectedFileName()
                os.remove(fn)
                self.protocolList.clearCache()
            except:
                sys.excepthook(*sys.exc_info())
                return
            finally:
                self.resetDeleteState()
    
    def resetDeleteState(self):
        self.deleteState = 0
        self.ui.deleteProtocolBtn.setText('Delete')
    
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
            self.fileName = fileName
            self.conf = readConfigFile(fileName)
            for d in self.conf['devices']:
                self.conf['devices'][d]['enabled'] = True
        else:
            self.fileName = None
            self.name = None
            self.conf = {'devices': {}, 'duration': 0.2, 'continuous': False}
        
    def generateProtocol(self, **args):
        """Generate the configuration data that will execute this protocol"""
        pass
    
    def write(self, fileName=None):
        ## Remove unused devices before writing
        rem = [d for d in self.conf['devices'] if not self.conf['devices'][d]['enabled']]
        for d in rem:
            del self.conf['devices'][d]
                
        if fileName is None:
            if self.fileName is None:
                raise Exception("Can not write protocol--no file name specified")
            fileName = self.fileName
        self.fileName = fileName
        writeConfigFile(self.conf, fileName)
    
    def enabledDevices(self):
        return [i for i in self.conf['devices'] if self.conf['devices'][i]['enabled']]
        
    def removeDevice(self, dev):
        if dev in self.conf['devices']:
            self.conf['devices'][dev]['enabled'] = False
        
    def addDevice(self, dev):
        if dev not in self.conf['devices']:
            self.conf['devices'][dev] = {}
        self.conf['devices'][dev]['enabled'] = True