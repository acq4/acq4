from __future__ import print_function
from acq4.util import Qt
from acq4.modules.Module import *
import sys, re, os, time, traceback
import acq4.util.debug as debug
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.console as console
import numpy as np


EDITOR = "pykate {fileName}:{lineNum}"

class Console(Module):
    moduleDisplayName = "Console"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager
        self.localNamespace = {
            'man': manager,
            'pg': pg,
            'np': np,
        }
        self.configFile = os.path.join('modules', 'Console.cfg')
        
        msg = """
        Python console built-in variables:
           man - The ACQ4 Manager object
                 man.currentFile  ## currently selected file
                 man.getCurrentDir()  ## current storage directory
                 man.getCurrentDatabase() ## currently selected database
                 man.getDevice("Name")
                 man.getModule("Name")
           pg - pyqtgraph library
                pg.show(imageData)
                pg.plot(plotData)
           np - numpy library
           
        """
        
        self.win = Qt.QMainWindow()
        mp = os.path.dirname(__file__)
        self.win.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
        self.win.resize(800,500)
        self.cw = ConsoleWidget(namespace=self.localNamespace, text=msg, editor=EDITOR, module=self)
        self.win.setCentralWidget(self.cw)
        self.win.setWindowTitle('ACQ4 Console')
        self.win.show()


## reimplement history save/restore methods
class ConsoleWidget(console.ConsoleWidget):
    def __init__(self, *args, **kargs):
        self.module = kargs.pop('module')
        console.ConsoleWidget.__init__(self, *args, **kargs)
        
    def saveHistory(self, history):
        self.module.manager.writeConfigFile({'history': history}, self.module.configFile)
        
    def loadHistory(self):
        config = self.module.manager.readConfigFile(self.module.configFile, missingOk=True)
        if 'history' in config:
            return config['history']
        

