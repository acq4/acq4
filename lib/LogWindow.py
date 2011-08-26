import time
import traceback

from PyQt4 import QtGui, QtCore
import LogWindowTemplate
from FeedbackButton import FeedbackButton
import configfile
from DataManager import DirHandle
#from lib.Manager import getManager

WIN = None

class LogButton(FeedbackButton):

    def __init__(self, *args):
        FeedbackButton.__init__(self, *args)
        #self.setMaximumHeight(30)
        global WIN
        self.clicked.connect(WIN.show)
        WIN.buttons.append(self)
        
        

class LogWindow(QtGui.QMainWindow):
    
    def __init__(self, manager):
        QtGui.QMainWindow.__init__(self)
        self.ui = LogWindowTemplate.Ui_MainWindow()
        self.ui.setupUi(self)
        self.resize(1000, 500)
        self.manager = manager
        global WIN
        WIN = self
        #self.msgCount = 0
        self.logCount=0
        self.fileName = 'tempLog.txt'
        configfile.writeConfigFile('', 'tempLog.txt')
        self.buttons = [] ## all Log Buttons get added to this list, so it's easy to make them all do things, like flash red.
        
        ## self.ui.input is a QLineEdit
        ## self.ui.output is a QPlainTextEdit
        
        self.ui.input.returnPressed.connect(self.textEntered)
        self.ui.setStorageDirBtn.clicked.connect(self.setStorageDir)
        
        
    def logMsg(self, msg, importance=5, msgType='status', exception=None, **kwargs):
        """msgTypes: user, status, error, warning
           importance: 0-9
           exception: holds a list of strings with the traceback"""
        
        currentDir = kwargs.get('currentDir', None)
        if currentDir is not None:
            kwargs.pop('currentDir')
        if isinstance(currentDir, DirHandle):
            currentDir = currentDir.name()
        now = str(time.strftime('%Y.%m.%d %H:%M:%S'))
        name = 'LogEntry_' + str(time.strftime('%Y.%m.%d %H.%M.%S'))
        #self.msgCount += 1
        entry = {}
        entry[name] = {}
        entry[name]['message'] = msg
        entry[name]['timestamp'] = now
        entry[name]['currentDir'] = currentDir
        entry[name]['importance'] = importance
        entry[name]['msgType'] = msgType
        entry[name]['exception'] = exception
        for k in kwargs:
            entry[name][k] = kwargs[k]
        self.saveEntry(entry)
        self.displayEntry(entry[name])
        
    def logExc(self, *args, **kwargs):
        self.flashButtons()
        error, tb = self.formatException(*args)
        self.logMsg(error, msgType='error', exception=tb)
        
        
    def textEntered(self):
        msg = str(self.ui.input.text())
        try:
            currentDir = self.manager.getCurrentDir()
        except:
            currentDir = None
        self.logMsg(msg, importance=8, msgType='user', currentDir=currentDir)
        self.ui.input.clear()
        
    #def enterModuleMessage(self, msg):
     #   self.displayText(msg, colorStr = 'green')
            
    def displayEntry(self, entry):
        if entry['msgType'] == 'user':
            self.displayText(entry['message'], colorStr='blue', timeStamp=entry['timestamp'])
        elif entry['msgType'] == 'status':
            if entry['importance'] > 7:
                colorStr = 'black'
            elif entry['importance'] < 4:
                colorStr = 'gray'
            else:
                colorStr = 'green'
            self.displayText(entry['message'], colorStr=colorStr, timeStamp=entry['timestamp'])
        elif entry['msgType'] == 'error':
            self.displayText(entry['message'], colorStr='red', timeStamp=entry['timestamp'])
            self.displayTraceback(entry['exception'])
        elif entry['msgType'] == 'warning':
            self.displayText(entry['message'], colorStr='orange', timeStamp=entry['timestamp'])
        else:
            self.displayText(entry['message'], colorStr='black', timeStamp=entry['timestamp'])
        
    def displayText(self, msg, colorStr = 'black', timeStamp=None):
        if timeStamp is not None:
            strn = '<i style="color:gray"> %s </i> <span style="color:%s"> %s </span> \n' % (timeStamp, colorStr, msg)
        else:
            strn = '<span style="color:%s"> %s </span> \n' % (colorStr, msg)
        self.ui.output.appendHtml(strn)
        
    def formatException(self, *args):
        tb = traceback.format_exception(*args)
        error = tb.pop(-1)
        return (error, tb)
        
    def displayTraceback(self, tb, color='grey'):
        #tb = traceback.format_exception(*args)
        #self.displayText(tb[0], 'red')
        lines = []
        indent = 4
        prefix = ''
        for l in ''.join(tb).split('\n'):
            if l == '':
                continue
            spaceCount = 0
            while l[spaceCount] == ' ':
                spaceCount += 1
            lines.append("&nbsp;"*(indent+spaceCount*2) + prefix + l)
        self.displayText('<br>'.join(lines), color)

    def flashButtons(self):
        for b in self.buttons:
            b.failure(tip='An error occurred. Please see the log.', limitedTime = False)
            
    def resetButtons(self):
        for b in self.buttons:
            b.reset()
        
    def setStorageDir(self):
        print x
        
    def show(self):
        QtGui.QMainWindow.show(self)
        self.activateWindow()
        self.raise_()
        self.resetButtons()
        
    def setLogDir(self, d):
        self.logMsg('Moving log storage to %s.' % (d.name(relativeTo=self.manager.baseDir) +'/log.txt'))
        oldfName = self.fileName
        self.fileName = d.name() + '/log.txt'
        if oldfName == 'tempLog.txt':
            temp = configfile.readConfigFile(oldfName)
            self.saveEntry(temp)
        self.logMsg('Moved log storage from %s to %s.' % (oldfName, self.fileName))
        self.ui.storageDirLabel.setText(self.fileName)
        self.manager.sigLogDirChanged.emit(d)
        
    def saveEntry(self, entry):
        ## in foldertypes.cfg make a way to specify a folder type as an experimental unit. Then whenever one of these units is created, give it a new log file (perhaps numbered if it's not the first one made in that run of the experiment?). Also, make a way in the Data Manager to specify where a log file is stored (so you can store it another place if you really want to...).  
        
        
        
        #if self.fileName == None:
            #i=0
            #self.fileName = self.manager.baseDir.name() + '/'+ str(time.strftime('%Y.%m.%d')) + '_Log.txt'
            ##configfile.writeConfigFile('', self.fileName)
        configfile.appendConfigFile(entry, self.fileName)
            
            
        
if __name__ == "__main__":
    import sys
    app = QtGui.QApplication([])
    log = LogWindow()
    log.show()
    original_excepthook = sys.excepthook
    
    def excepthook(*args):
        global original_excepthook
        log.displayException(*args)
        ret = original_excepthook(*args)
        sys.last_traceback = None           ## the important bit
        
    
    sys.excepthook = excepthook

    app.exec_()