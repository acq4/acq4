from PyQt4 import QtCore, QtGui
from lib.modules.Module import *
import sys, re, os
import debug
import traceback
import pyqtgraph as pg
import numpy as np
import template
        

class Console(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager
        self.locals = {
            'man': manager,
            'pg': pg,
            'np': np,
        }
        self.configFile = os.path.join('modules', 'Console.cfg')
        config = manager.readConfigFile(self.configFile, missingOk=True)
        
        self.multiline = None
        self.inCmd = False
        
        self.win = QtGui.QMainWindow()
        self.win.setWindowTitle('ACQ4 Console')
        self.win.resize(800,500)
        self.win.show()
        self.cw = QtGui.QWidget()
        self.win.setCentralWidget(self.cw)
        
        self.ui = template.Ui_Form()
        self.ui.setupUi(self.cw)
        self.output = self.ui.output
        self.input = self.ui.input
        self.input.setFocus()
        #self.layout = QtGui.QVBoxLayout()
        #self.cw.setLayout(self.layout)
        #self.output = QtGui.QPlainTextEdit()
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
        #self.output.setReadOnly(True)
        #self.layout.addWidget(self.output)
        #self.input = CmdInput()
        if 'history' in config:
            self.input.history = [""] + config['history']
            self.ui.historyList.addItems(config['history'][::-1])
        #self.layout.addWidget(self.input)
        self.ui.historyList.hide()
        
        self.input.sigExecuteCmd.connect(self.runCmd)
        self.ui.historyBtn.toggled.connect(self.ui.historyList.setVisible)
        self.ui.historyList.itemClicked.connect(self.cmdSelected)
        self.ui.historyList.itemDoubleClicked.connect(self.cmdDblClicked)
        
    def runCmd(self, cmd):
        #cmd = str(self.input.lastCmd)
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        encCmd = re.sub(r'>', '&gt;', re.sub(r'<', '&lt;', cmd))
        encCmd = re.sub(r' ', '&nbsp;', encCmd)
        
        self.ui.historyList.addItem(cmd)

        self.manager.writeConfigFile({'history': self.input.history[1:100]}, self.configFile)
        
        try:
            sys.stdout = self
            sys.stderr = self
            if self.multiline is not None:
                self.write("<br><b>%s</b>\n"%encCmd, html=True)
                self.execMulti(cmd)
            else:
                self.write("<br><div style='background-color: #CCF'><b>%s</b>\n"%encCmd, html=True)
                self.inCmd = True
                self.execSingle(cmd)
            
            if not self.inCmd:
                self.write("</div>\n", html=True)
                
        finally:
            sys.stdout = self.stdout
            sys.stderr = self.stderr
            
            sb = self.output.verticalScrollBar()
            sb.setValue(sb.maximum())
            sb = self.ui.historyList.verticalScrollBar()
            sb.setValue(sb.maximum())
            
    def execSingle(self, cmd):
        try:
            output = eval(cmd, globals(), self.locals)
            self.write(str(output) + '\n')
        except SyntaxError:
            try:
                exec(cmd, globals(), self.locals)
            except SyntaxError as exc:
                if 'unexpected EOF' in exc.msg:
                    self.multiline = cmd
                else:
                    self.displayException()
            except:
                self.displayException()
        except:
            self.displayException()
            
            
    def execMulti(self, nextLine):
        self.stdout.write(nextLine+"\n")
        if nextLine.strip() != '':
            self.multiline += "\n" + nextLine
            return
        else:
            cmd = self.multiline
            
        try:
            output = eval(cmd, globals(), self.locals)
            self.write(str(output) + '\n')
            self.multiline = None
        except SyntaxError:
            try:
                exec(cmd, globals(), self.locals)
                self.multiline = None
            except SyntaxError as exc:
                if 'unexpected EOF' in exc.msg:
                    self.multiline = cmd
                else:
                    self.displayException()
                    self.multiline = None
            except:
                self.displayException()
                self.multiline = None
        except:
            self.displayException()
            self.multiline = None

    def write(self, strn, html=False):
        self.output.moveCursor(QtGui.QTextCursor.End)
        if html:
            self.output.textCursor().insertHtml(strn)
        else:
            if self.inCmd:
                self.inCmd = False
                self.output.textCursor().insertHtml("</div><br><div style='font-weight: normal; background-color: #FFF;'>")
                #self.stdout.write("</div><br><div style='font-weight: normal; background-color: #FFF;'>")
            self.output.insertPlainText(strn)
        self.stdout.write(strn)
            
    def displayException(self):
        tb = traceback.format_exc()
        lines = []
        indent = 4
        prefix = '' 
        for l in tb.split('\n'):
            lines.append(" "*indent + prefix + l)
        self.write('\n'.join(lines))
        
    def cmdSelected(self, item):
        index = -(self.ui.historyList.row(item)+1)
        self.input.setHistory(index)
        self.input.setFocus()
        
    def cmdDblClicked(self, item):
        index = -(self.ui.historyList.row(item)+1)
        self.input.setHistory(index)
        self.input.execCmd()
        
    
    
    
    
    