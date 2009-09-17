from lib.modules.Module import *
from ManagerTemplate import Ui_MainWindow
from PyQt4 import QtCore, QtGui
import sys, os
from lib.util import configfile

class Manager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.win = QtGui.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.stateFile = os.path.join('config', 'managerState.cfg')

        self.devRackDocks = {}
        for d in self.manager.listDevices():
            try:
                dw = self.manager.getDevice(d).deviceInterface()
                dock = QtGui.QDockWidget(d)
                dock.setFeatures(dock.AllDockWidgetFeatures)
                dock.setObjectName(d)
                dock.setWidget(dw)
                
                self.devRackDocks[d] = dock
                self.win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
            except:
                print "Error while creating dock for device '%s':" % d
                sys.excepthook(*sys.exc_info())

        self.updateModList()
        self.updateConfList()
        
        QtCore.QObject.connect(self.ui.loadConfigBtn, QtCore.SIGNAL('clicked()'), self.loadConfig)
        QtCore.QObject.connect(self.ui.loadModuleBtn, QtCore.SIGNAL('clicked()'), self.loadModule)
        QtCore.QObject.connect(self.ui.configList, QtCore.SIGNAL('itemDoubleClicked(QListWidgetItem*)'), self.loadConfig)
        QtCore.QObject.connect(self.ui.moduleList, QtCore.SIGNAL('itemDoubleClicked(QListWidgetItem*)'), self.loadModule)
        QtCore.QObject.connect(self.ui.quitBtn, QtCore.SIGNAL('clicked()'), self.requestQuit)
        self.win.show()

        if os.path.exists(self.stateFile):
            state = configfile.readConfigFile(self.stateFile)
            ws = QtCore.QByteArray.fromPercentEncoding(state['window'])
            self.win.restoreState(ws)
        
    def updateModList(self):
        self.ui.moduleList.clear()
        for m in self.manager.listDefinedModules():
            self.ui.moduleList.addItem(m)
            
    def updateConfList(self):
        self.ui.configList.clear()
        for m in self.manager.listConfigurations():
            self.ui.configList.addItem(m)
        
    def show(self):
        self.win.show()

    def requestQuit(self):
        self.manager.quit()
        
    def loadModule(self):
        mod = str(self.ui.moduleList.currentItem().text())
        self.manager.loadDefinedModule(mod)
        
    def loadConfig(self):
        cfg = str(self.ui.configList.currentItem().text())
        self.manager.loadDefinedConfig(cfg)
        self.updateModList()

    def quit(self):
        ## save ui configuration
        state = {'window': str(self.win.saveState().toPercentEncoding())}
        configfile.writeConfigFile(state, self.stateFile)
