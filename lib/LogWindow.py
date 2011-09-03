import time
import traceback
import sys

from PyQt4 import QtGui, QtCore
import LogWindowTemplate
from FeedbackButton import FeedbackButton
import configfile
from DataManager import DirHandle
from HelpfulException import HelpfulException
from Mutex import Mutex
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
    
    sigDisplayEntry = QtCore.SIGNAL(object) ## for thread-safetyness
    
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
        self.logFile = None
        configfile.writeConfigFile('', self.fileName())  ## start a new temp log file, destroying anything left over from the last session.
        self.buttons = [] ## all Log Buttons get added to this list, so it's easy to make them all do things, like flash red.
        self.lock = Mutex()
        
        ## self.ui.input is a QLineEdit
        ## self.ui.output is a QPlainTextEdit
        
        self.ui.input.returnPressed.connect(self.textEntered)
        self.ui.setStorageDirBtn.clicked.connect(self.setStorageDir)
        self.sigDisplayEntry.connect(self.displayEntry)
        
        
    def logMsg(self, msg, importance=5, msgType='status', exception=(None,None,None), **kwargs):
        """msgTypes: user, status, error, warning
           importance: 0-9
           exception: a tuple (type, exception, traceback) as returned by sys.exc_info()
        """

        
        try:
            currentDir = self.manager.getCurrentDir()
        except:
            currentDir = None
        if isinstance(currentDir, DirHandle):
            kwargs['currentDir'] = currentDir.name()
        
        now = str(time.strftime('%Y.%m.%d %H:%M:%S'))
        name = 'LogEntry_' + str(time.strftime('%Y.%m.%d %H.%M.%S'))  ## TODO: not unique
        #self.msgCount += 1
        entry = {
            'docs': None,
            'reasons': None,
            'message': msg,
            'timestamp': now,
            'importance': importance,
            'msgType': msgType,
            'exception': exception,
        }
        for k in kwargs:
            entry[k] = kwargs[k]
        self.processEntry(entry)
        self.saveEntry({name:entry})
        self.displayEntry(entry)
        
        
    def logExc(self, *args, **kargs):
        kargs['exception'] = sys.exc_info()
        self.logMsg(*args, **kargs)
        
    def processEntry(self, entry):
        ## pre-processing common to saveEntry and displayEntry
        if entry['msgType'] == 'error':
            exc_info = entry.pop('exception')
            exTyp, exc, tb = exc_info
            if isinstance(exc, HelpfulException):
                error, tb, docs = self.formatHelpfulException(*exc_info)
                entry['message'] += error
                entry['docs'] += docs
                #self.logMsg(error, msgType='error', exception=tb, documentation=docs **kwargs)
            else: 
                error, tb = self.formatException(*exc_info)
                entry['message'] += '\n' + error
                #entry['msgType'] = 'error'
                #self.logMsg(message+error, msgType='error', exception=tb, **kwargs)
            entry['traceback'] = tb
        
    #def logExc(self, *args, **kwargs):
        #self.flashButtons()
        #exc_info = kwargs.pop('exc_info', sys.exc_info())
        #exc = exc_info[1]
        #if isinstance(exc, HelpfulException):
            #error, tb, docs = self.formatHelpfulException(*exc_info)
            #self.logMsg(error, msgType='error', exception=tb, documentation=docs **kwargs)
        #else: 
            #message = kwargs.get('message', '')
            #if message is not '':
                #kwargs.pop('message')
                #message += '\n'
            #error, tb = self.formatException(*exc_info)
            #self.logMsg(message+error, msgType='error', exception=tb, **kwargs)
    
        
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
        isGuiThread = QtCore.QThread.currentThread() == QtCore.QCoreApplication.instance().thread()
        if not isGuiThread:
            sigDisplayEntry.emit(entry)
            return
        
        else:
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
                self.displayText(entry['message'], colorStr='#AA0000', timeStamp=entry['timestamp'], reasons=entry.get('reasons', None), docs=entry.get('documentation', None))
                self.displayTraceback(entry['traceback'])
                self.flashButtons()
                
            elif entry['msgType'] == 'warning':
                self.displayText(entry['message'], colorStr='orange', timeStamp=entry['timestamp'])
            else:
                self.displayText(entry['message'], colorStr='black', timeStamp=entry['timestamp'])
        
    def displayText(self, msg, colorStr = 'black', timeStamp=None, reasons=None, docs=None):
        if reasons is not None:
            msg += "Reasons: " + reasons + '\n'
        if docs is not None:
            msg += "Documentation: " + docs
        if msg[-1:] == '\n':
            msg = msg[:-1]     
        msg = '<br>'.join(msg.split('\n'))
        if timeStamp is not None:
            strn = '<b style="color:black"> %s </b> <span style="color:%s"> %s </span> \n' % (timeStamp, colorStr, msg)
        else:
            strn = '<span style="color:%s"> %s </span> \n' % (colorStr, msg)
        self.ui.output.appendHtml(strn)
        
    def formatException(self, *args):
        tb = traceback.format_exception(*args)
        error = tb.pop(-1)
        return (error,tb)
    
    def formatHelpfulException(self, *args):
        ### so ugly.....
        number = 1
        tbs = []
        errors, tbs = self.formatException(*args)
        tbs.insert(0, str(number)+'. ')
        errors = str(number) + '. ' + exc.messages[0]
        errors += '  Reasons: ' 
        for i in exc.reasons[0]:
            errors += str(i) + ' '
        errors += '\n More documentation at: ', exc.docs[0]
        for i, e in enumerate(exc.excs):
            number += 1
            error, tb = self.formatException(*e)
            if e != exc.excs[-1]:
                errors += str(number) + '. ' + exc.messages[i+1]
                errors += '  Reasons: '
                for i in exc.reasons[i+1]:
                    errors += str(i) + ' '
                errors += '\n More documentation at: ', exc.docs[i+1]                
            else:
                errors += str(number) + '. ' + error
            tbs.append(str(number) + '. ')
            tbs.extend(tb) 
        return (errors, tbs)
        
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
        try:
            #self.makeError()
            print x
        except:
            t, exc, tb = sys.exc_info()
            self.manager.logExc(message="This button doesn't work", reasons='reason a, reason b', docs='documentation')
            #if isinstance(exc, HelpfulException):
                #exc.prependErr("Button doesn't work", (t,exc,tb), "a. It's supposed to raise an error for testing purposes, b. You're doing it wrong.")
                #raise
            #else:
                #raise HelpfulException(message='This button does not work.', exc=(t, exc, tb), reasons="a. It's supposed to raise an error for testing purposes, b. You're doing it wrong.")
    
    def makeError(self):
        try:
            print x
        except:
            t, exc, tb = sys.exc_info()
            if isinstance(exc, HelpfulException):
                exc.prependErr("msg from makeError", (t,exc,tb), ["a. mkErr reason one", "b. mkErr reason 2"])
                raise
            else:
                raise HelpfulException(message='msg from makeError', exc=(t, exc, tb), reasons=["a. reason one", "b. reason 2"])
            
    def show(self):
        QtGui.QMainWindow.show(self)
        self.activateWindow()
        self.raise_()
        self.resetButtons()
        
    def fileName(self):
        ## return the log file currently used
        if self.logFile is None:
            return "tempLog.txt"
        else:
            return self.logFile.name()
        
    def setLogDir(self, dh):
        oldfName = self.fileName()
        
        self.logMsg('Moving log storage to %s.' % (self.logFile.name(relativeTo=self.manager.baseDir))) ## make this note before we change the log file, so when a log ends, you know where it went after.
        
        if dh.exists('log.txt'):
            self.logFile = dh['log.txt']
        else:
            self.logFile = dh.createFile('log.txt')
        
        
        if oldfName == 'tempLog.txt':
            temp = configfile.readConfigFile(oldfName)
            self.saveEntry(temp)
        self.logMsg('Moved log storage from %s to %s.' % (oldfName, self.fileName()))
        self.ui.storageDirLabel.setText(self.fileName())
        self.manager.sigLogDirChanged.emit(dh)
        
    def getLogDir(self):
        if self.logFile is None:
            return None
        else:
            return self.logFile.parent()
        
    def saveEntry(self, entry):
        ## in foldertypes.cfg make a way to specify a folder type as an experimental unit. Then whenever one of these units is created, give it a new log file (perhaps numbered if it's not the first one made in that run of the experiment?). Also, make a way in the Data Manager to specify where a log file is stored (so you can store it another place if you really want to...).  
        with self.lock():
            configfile.appendConfigFile(entry, self.fileName())
            
            
        
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