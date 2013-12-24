

import acq4.LogWidgetTemplate
from PyQt4 import QtGui, QtCore
import acq4.Manager
from acq4.LogWindow import LogWidget
import acq4.util.configfile as cf
import acq4.util.debug as debug

class FileLogView(LogWidget):
    
    def __init__(self, parent, mod):
        #QtGui.QWidget.__init__(self, parent)
        #self.manager = acq4.Manager.getManager()
        #self.wid = LogWidget(self, self.manager)
        LogWidget.__init__(self, parent, acq4.Manager.getManager())
        
        #self.ui = lib.LogWidgetTemplate.Ui_Form()
        #self.ui.setupUi(self)
        
        #self.ui.input.hide()
        
        #self.logPrinter = LogPrinter(self.ui.output)
        
        self.currentLogDir = None ## will be set to a dh when a file is selected in Data Manager
        self.mod = mod
        
    #def clear(self):
        #self.ui.logView.clear()
        #pass
    
    def selectedFileChanged(self, dh):
        """Finds the log file associated with dh (a FileHandle or DirHandle). Checks dh and all (grand)parent directories
        until a log.txt file is found, and passes that file on to be displayed. If no log.txt file is found, then nothing is displayed."""
        ## make sure a file is actually selected
        if dh is None:
            self.clear()
            self.currentLogDir = None
            self.dirFilter = False
            return
        
        ## check dh and parents for a log.txt file
        if not dh.isDir():
            dh = dh.parent()
        logDir = None 
        p = dh
        while p != self.mod.baseDir: 
            if p.exists('log.txt'):
                logDir = p
                break
            else:
                p = p.parent()
        
        ## if we're already displaying that log file, stop here, otherwise set/display the log file
        if logDir == self.currentLogDir:
            self.updateDirFilter(dh)
            self.filterEntries()
        else:
            self.currentLogDir = logDir
            self.setCurrentLog(logDir)
        
    #def selectedFileChanged(self, dh):
        #if dh is None:
            #self.clear()
            #self.currentLogDir = None
            #return
    
        #checkChildren = True
        #if not dh.isDir():
            #dh = dh.parent()
            #checkChildren = False
            
        #logDirs = []
        
        #p = dh
        #while p != self.mod.baseDir: ## so that for now we only ever deal with one logFile
            #if p.exists('log.txt'):
                #logDirs.append(p)
                #break
            #p = p.parent()
            
        #checkChildren = False  ## so that for now we only deal with one log file  
        #if checkChildren:
            #subDirs = [dh.getFile(f) for f in dh.subDirs()]
            #newSubDirs = []
            #while len(subDirs) > 0:
                #for sd in subDirs:
                    #if sd.exists('log.text'):
                        #logDirs.append(sd)
                    #if len(sd.subDirs()) > 0:
                        #newSubDirs += [sd.getFile(f) for f in sd.subDirs()]
                #subDirs = newSubDirs
                #newSubDirs = []
                
        #if logDirs[0] == self.currentLogDir:
            #return
        #else:
            #self.currentLogDir = logDirs[0]
            #if len(logDirs) !=0:
                #self.setCurrentLog(logDirs[0])
            #else:
                #self.clear()
                #self.ui.dirLabel.setText("")

    def setCurrentLog(self, dh):
        if dh is not None:
            try:
                self.loadFile(dh['log.txt'].name())
                self.ui.dirLabel.setText("Currently displaying " + self.currentLogDir.name(relativeTo=self.manager.baseDir)+'/log.txt')    
            except:
                debug.printExc("Error loading log file:")
                self.clear()
                self.ui.dirLabel.setText("")
        else:
            self.clear()
            self.ui.dirLabel.setText("")
        
    def orderLogEntries(self):
        pass
    
    #def readCurrentLog(self):
        #return cf.readConfigFile(self.currentLogDir.name()+'/log.txt')
            