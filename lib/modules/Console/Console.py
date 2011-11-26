from PyQt4 import QtCore, QtGui
from lib.modules.Module import *
import sys, debug
import traceback
import pyqtgraph as pg
import numpy as np
import re

class CmdInput(QtGui.QLineEdit):
    def __init__(self):
        QtGui.QLineEdit.__init__(self)
        self.history = [""]
        self.ptr = 0
        self.lastCmd = None
    
    def keyPressEvent(self, ev):
        #print "press:", ev.key(), QtCore.Qt.Key_Up, QtCore.Qt.Key_Down, QtCore.Qt.Key_Enter
        if ev.key() == QtCore.Qt.Key_Up and self.ptr < len(self.history) - 1:
            self.ptr += 1
            self.setText(self.history[self.ptr])
            ev.accept()
            return
        elif ev.key() ==  QtCore.Qt.Key_Down and self.ptr > 0:
            self.ptr -= 1
            self.setText(self.history[self.ptr])
            ev.accept()
            return
        elif ev.key() == QtCore.Qt.Key_Return:
            cmd = self.text()
            if len(self.history) == 1 or cmd != self.history[1]:
                self.history.insert(1, cmd)
            self.ptr = 0
            self.lastCmd = cmd
            self.setText("")
        QtGui.QLineEdit.keyPressEvent(self, ev)
        

class Console(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.locals = {
            'man': manager,
            'pg': pg,
            'np': np,
        }
        self.win = QtGui.QMainWindow()
        self.win.resize(800,500)
        self.win.show()
        self.cw = QtGui.QWidget()
        self.win.setCentralWidget(self.cw)
        self.layout = QtGui.QVBoxLayout()
        self.cw.setLayout(self.layout)
        self.output = QtGui.QPlainTextEdit()
        self.output.setPlainText("""
        Python console built-in variables:
           man - The ACQ4 Manager object
                 man.currentFile  ## currently selected file
                 man.getCurrentDir()  ## current storage directory
                 man.getDevice("Name")
                 man.getModule("Name")
           pg - pyqtgraph library
                pg.show(imageData)
                pg.plot(plotData)
           np - numpy library
           
        """)
        self.output.setReadOnly(True)
        self.layout.addWidget(self.output)
        self.input = CmdInput()
        self.layout.addWidget(self.input)
        self.input.returnPressed.connect(self.runCmd)
        
    def runCmd(self):
        cmd = str(self.input.lastCmd)
        stdout = sys.stdout
        stderr = sys.stderr
        encCmd = re.sub(r'>', '&gt;', re.sub(r'<', '&lt;', cmd))
        self.write("<b>&gt; %s</b>\n"%encCmd, html=True)
        try:
            sys.stdout = self
            sys.stderr = self
            
            output = eval(cmd, globals(), self.locals)
            self.write(str(output) + '\n')
        except SyntaxError:
            try:
                exec(cmd, globals(), self.locals)
            except:
                self.displayException()
        except:
            self.displayException()
        finally:
            sys.stdout = stdout
            sys.stderr = stderr
            sb = self.output.verticalScrollBar()
            sb.setValue(sb.maximum())
            
    def write(self, strn, html=False):
        if html:
            self.output.appendHtml(strn)
            
        else:
            self.output.appendPlainText(strn)
            
    def displayException(self):
        tb = traceback.format_exc()
        lines = []
        indent = 4
        prefix = '' 
        for l in tb.split('\n'):
            lines.append(" "*indent + prefix + l)
        self.write('\n'.join(lines))
        
    
    #def showException(self):
        #text = debug.getExc()
        #self.
    
    
    
    
    