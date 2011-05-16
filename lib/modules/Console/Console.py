from PyQt4 import QtCore, QtGui
from lib.modules.Module import *
import sys, debug

class Console(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.locals = {}
        self.win = QtGui.QMainWindow()
        self.win.resize(800,500)
        self.win.show()
        self.cw = QtGui.QWidget()
        self.win.setCentralWidget(self.cw)
        self.layout = QtGui.QVBoxLayout()
        self.cw.setLayout(self.layout)
        self.output = QtGui.QTextEdit()
        self.output.setReadOnly(True)
        self.layout.addWidget(self.output)
        self.input = QtGui.QLineEdit()
        self.layout.addWidget(self.input)
        self.input.returnPressed.connect(self.runCmd)
        
    def runCmd(self):
        cmd = self.input.text()
        stdout = sys.stdout
        stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
        self.write("<b>&gt; %s</b>\n"%cmd, html=True)
        try:
            output = eval(cmd, globals(), self.locals)
            self.write(str(output) + '\n')
        except SyntaxError:
            exec(cmd, globals(), self.locals)
        finally:
            sys.stdout = stdout
            sys.stderr = stderr
            
    def write(self, strn, html=False):
        if html:
            self.output.appendHtml(strn)
            
        else:
            self.output.appendPlainText(strn)
    
    
    #def showException(self):
        #text = debug.getExc()
        #self.
    
    
    
    
    