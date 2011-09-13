

import lib.LogWidgetTemplate
from PyQt4 import QtGui, QtCore
import lib.Manager
from lib.LogWindow import LogWidget
import configfile as cf

class FileLogView(LogWidget):
    
    def __init__(self, parent, mod):
        LogWidget.__init__(self, parent)
        self.manager = lib.Manager.getManager()
        #self.ui = lib.LogWidgetTemplate.Ui_Form()
        #self.ui.setupUi(self)
        
        #self.ui.input.hide()
        
        #self.logPrinter = LogPrinter(self.ui.output)
        
        self.currentLogDirs = None
        self.mod = mod
        
    def clear(self):
        self.ui.output.clear()
    
        
    def selectedFileChanged(self, dh):
        if dh is None:
            self.clear()
            self.currentLogDirs = None
            return
    
        checkChildren = True
        if not dh.isDir():
            dh = dh.parent()
            checkChildren = False
            
        logDirs = []
        
        p = dh
        while p != self.mod.baseDir and len(logDirs) < 1: ## so that for now we only ever deal with one logFile
            if p.exists('log.txt'):
                logDirs.append(p)
            p = p.parent()
            
        checkChildren = False  ## so that for now we only deal with one log file  
        if checkChildren:
            subDirs = [dh.getFile(f) for f in dh.subDirs()]
            newSubDirs = []
            while len(subDirs) > 0:
                for sd in subDirs:
                    if sd.exists('log.text'):
                        logDirs.append(sd)
                    if len(sd.subDirs()) > 0:
                        newSubDirs += [sd.getFile(f) for f in sd.subDirs()]
                subDirs = newSubDirs
                newSubDirs = []
                
        if logDirs == self.currentLogDirs:
            return
        else:
            self.currentLogDirs = logDirs
            if len(self.currentLogDirs) !=0:
                self.setCurrentLog()
            else:
                self.clear()
                self.ui.dirLabel.setText("")

    def setCurrentLog(self):
        if len(self.currentLogDirs) > 1:
            entries = self.orderLogEntries()
        else:
            entries = self.readCurrentLog()
            
        self.clear()
        for k in entries:
            self.displayEntry(entries[k])
        self.ui.dirLabel.setText("Currently displaying " + self.currentLogDirs[0].name(relativeTo=self.manager.baseDir)+'/log.txt')
            
    def orderLogEntries(self):
        pass
    
    def readCurrentLog(self):
        return cf.readConfigFile(self.currentLogDirs[0].name()+'/log.txt')
            