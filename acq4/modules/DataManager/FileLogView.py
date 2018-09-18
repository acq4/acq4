from __future__ import print_function


from acq4.util import Qt
import acq4.Manager
from acq4.util.LogWindow import LogWidget
import acq4.util.configfile as cf
import acq4.util.debug as debug


class FileLogView(LogWidget):
    
    def __init__(self, parent, mod):
        LogWidget.__init__(self, parent, acq4.Manager.getManager())
        
        self.currentLogDir = None ## will be set to a dh when a file is selected in Data Manager
        self.mod = mod
    
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
            