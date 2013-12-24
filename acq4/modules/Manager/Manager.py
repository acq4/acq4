# -*- coding: utf-8 -*-
from acq4.modules.Module import *
from ManagerTemplate import Ui_MainWindow
from PyQt4 import QtCore, QtGui
import sys, os
import acq4.util.configfile as configfile
from acq4.util.debug import *

class Manager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.win = QtGui.QMainWindow()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        self.stateFile = os.path.join('modules', self.name + '_ui.cfg')

        self.devRackDocks = {}
        for d in self.manager.listDevices():
            try:
                dw = self.manager.getDevice(d).deviceInterface(self)
                if dw is None:
                    continue
                dock = QtGui.QDockWidget(d)
                dock.setFeatures(dock.DockWidgetMovable | dock.DockWidgetFloatable)
                dock.setObjectName(d)
                dock.setWidget(dw)
                
                self.devRackDocks[d] = dock
                self.win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
            except:
                self.showMessage("Error creating dock for device '%s', see console for details." % d, 10000)
                printExc("Error while creating dock for device '%s':" % d)

        self.updateModList()
        self.updateConfList()

        #QtCore.QObject.connect(self.ui.loadConfigBtn, QtCore.SIGNAL('clicked()'), self.loadConfig)
        self.ui.loadConfigBtn.clicked.connect(self.loadConfig)
        #QtCore.QObject.connect(self.ui.loadModuleBtn, QtCore.SIGNAL('clicked()'), self.loadModule)
        self.ui.loadModuleBtn.clicked.connect(self.loadModule)
        #QtCore.QObject.connect(self.ui.reloadModuleBtn, QtCore.SIGNAL('clicked()'), self.reloadAll)
        self.ui.reloadModuleBtn.clicked.connect(self.reloadAll)
        #QtCore.QObject.connect(self.ui.configList, QtCore.SIGNAL('itemDoubleClicked(QListWidgetItem*)'), self.loadConfig)
        self.ui.configList.itemDoubleClicked.connect(self.loadConfig)
        #QtCore.QObject.connect(self.ui.moduleList, QtCore.SIGNAL('itemDoubleClicked(QListWidgetItem*)'), self.loadModule)
        self.ui.moduleList.itemDoubleClicked.connect(self.loadModule)
        #self.logBtn = self.ui.logBtn ## to be able to access logBtns uniformly in all modules
        #self.logBtn.clicked.connect(manager.logWindow.show)
        #QtCore.QObject.connect(self.ui.quitBtn, QtCore.SIGNAL('clicked()'), self.requestQuit)
        self.ui.quitBtn.clicked.connect(self.requestQuit)

        state = self.manager.readConfigFile(self.stateFile)
        if 'geometry' in state:
            geom = QtCore.QRect(*state['geometry'])
            self.win.setGeometry(geom)
        if 'window' in state:
            ws = QtCore.QByteArray.fromPercentEncoding(state['window'])
            self.win.restoreState(ws)

        self.win.show()

        
    def showMessage(self, *args):
        self.ui.statusBar.showMessage(*args)
        
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
        try:
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
            mod = str(self.ui.moduleList.currentItem().text())
            self.manager.loadDefinedModule(mod)
            self.showMessage("Loaded module '%s'." % mod, 10000)
        finally:
            QtGui.QApplication.restoreOverrideCursor()
        
    def reloadAll(self):
        self.manager.reloadAll()
        #mod = str(self.ui.moduleList.currentItem().text())
        #self.manager.loadDefinedModule(mod, forceReload=True)
        #self.showMessage("Loaded module '%s'." % mod, 10000)
        
    def loadConfig(self):
        #print "LOAD CONFIG"
        cfg = str(self.ui.configList.currentItem().text())
        self.manager.loadDefinedConfig(cfg)
        self.updateModList()
        self.showMessage("Loaded configuration '%s'." % cfg, 10000)

    def quit(self):
        ## save ui configuration
        geom = self.win.geometry()
        state = {'window': str(self.win.saveState().toPercentEncoding()), 'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        self.manager.writeConfigFile(state, self.stateFile)
        Module.quit(self)
