# -*- coding: utf-8 -*-
from lib.modules.Module import Module
from lib.util.DirTreeModel import *
from AnalysisTemplate import *


class Analysis(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        
        self.win = QtGui.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.win)
        
        self.dataSource = None
        
        self.win.show()
        
        self.updateSourceList()
        self.updateModList()
        
        self.protocolList = DirTreeModel(self.manager.config['protocolDir'])
        self.ui.protocolList.setModel(self.protocolList)
        
        QtCore.QObject.connect(self.manager, QtCore.SIGNAL('modulesChanged'), self.updateSourceList)
        QtCore.QObject.connect(self.ui.dataSourceCombo, QtCore.SIGNAL('currentIndexChanged(QString)'), self.dataSourceChanged)
        QtCore.QObject.connect(self.ui.removeDataBtn, QtCore.SIGNAL('clicked()'), self.removeDataClicked)
        
    def updateModList(self):
        mods = self.listModules()
        self.ui.modsAvailableList.clear()
        for m in mods:
            self.ui.modsAvailableList.addItem(m)
        
    def dataSourceChanged(self, source):
        mod = self.manager.getModule(mod)
        self.connectDataSource(mod)
    
    def connectDataSource(self, mod):
        self.disconnectDataSource()
        QtCore.QObject.connect(mod, QtCore.SIGNAL('newFrame'), self.newFrame)
        QtCore.QObject.connect(mod, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)
        QtCore.QObject.connect(mod, QtCore.SIGNAL('taskStarted'), self.taskStarted)
        QtCore.QObject.connect(mod, QtCore.SIGNAL('protocolFinished'), self.protocolFinished)
        self.dataSource = mod
        
    def disconnectDataSource(self):
        if self.dataSource is None:
            return
        QtCore.QObject.disconnect(self.dataSource, QtCore.SIGNAL('newFrame'), self.newFrame)
        QtCore.QObject.disconnect(self.dataSource, QtCore.SIGNAL('protocolStarted'), self.protocolStarted)
        QtCore.QObject.disconnect(self.dataSource, QtCore.SIGNAL('taskStarted'), self.taskStarted)
        QtCore.QObject.disconnect(self.dataSource, QtCore.SIGNAL('protocolFinished'), self.protocolFinished)
        self.dataSource = None
        
    def protocolStarted(self):
        pass
    
    def taskStarted(self):
        pass
    
    def newFrame(self, frame):
        pass
    
    def protocolFinished(self):
        pass
    
    def listModules(self):
        rootDir = os.path.split(__file__)[0]
        modDir =  os.path.join(rootDir, 'modules')
        subd = os.listdir(modDir)
        mods = filter(lambda d: d[0] != '.' and os.path.isdir(os.path.join(modDir, d)), subd)
        return mods
    
    def removeDataClicked(self):
        pass
        
    def updateSourceList(self):
        for m in self.manager.listModules():
            self.ui.dataSourceCombo.addItem(m)
        
    def window(self):
        return self.win
    
    def quit(self):
        self.disconnectDataSource()
        Module.quit(self)
        
    
