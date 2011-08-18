import time
import traceback

from PyQt4 import QtGui, QtCore
import LogWindowTemplate



class LogWindow(QtGui.QMainWindow):
    
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.ui = LogWindowTemplate.Ui_MainWindow()
        self.ui.setupUi(self)
        #self.resize(800, 500)
        #self.cw = QtGui.QWidget()
        #self.setCentralWidget(self.cw)
        #self.layout = QtGui.QVBoxLayout()
        #self.cw.setLayout(self.layout)
        #self.output = QtGui.QPlainTextEdit()
        #self.output.setReadOnly(True)
        #self.layout.addWidget(self.output)
        #self.input = QtGui.QLineEdit()
        #self.layout.addWidget(self.input)
        ## self.ui.input is a QLineEdit
        ## self.ui.output is a QPlaitTextEdit
        
        self.ui.input.returnPressed.connect(self.enterText)
        self.ui.setStorageDirBtn.clicked.connect(self.setStorageDir)
        
    def enterText(self):
        msg = str(self.ui.input.text())
        self.displayText(msg, 'blue')
        self.ui.input.clear()
            
    def displayText(self, msg, colorStr = 'black', timeStamp=True):
        if timeStamp:
            now = str(time.strftime('%Y.%m.%d %H:%M:%S'))
            strn = '<i style="color:gray"> %s </i> <span style="color:%s"> %s </span> \n' % (now, colorStr, msg)
        else:
            strn = '<span style="color:%s"> %s </span> \n' % (colorStr, msg)
        self.ui.output.appendHtml(strn)
        
            
    def displayException(self, *args):
        #print "args: ", args 
        #tb = traceback.format_tb(tb)
        #print "tb 2: ", tb
        tb = traceback.format_exception(*args)
        #print "tb 3: ", tb
        self.displayText(tb[-1], 'red')
        lines = []
        indent = 4
        prefix = ''
        for l in ''.join(tb[:-1]).split('\n'):
            if l == '':
                continue
            spaceCount = 0
            while l[spaceCount] == ' ':
                spaceCount += 1
            lines.append("&nbsp;"*(indent+spaceCount*2) + prefix + l)
        #print "lines: ", lines
        self.displayText('<br>'.join(lines), 'grey', timeStamp = False)
        #self.displayText('<br>'.join(tb), 'green')
        
    def setStorageDir(self):
        print x
        
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