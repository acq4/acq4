from __future__ import print_function

import os
import numpy as np
import pyqtgraph as pg
import pyqtgraph.console as console
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.codeEditor import codeEditorCommand


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
        self.stateFile = os.path.join('modules', self.name + '_ui.cfg')
        
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
        self.cw = ConsoleWidget(namespace=self.localNamespace, text=msg, editor=codeEditorCommand(), module=self)
        self.win.setCentralWidget(self.cw)
        self.win.setWindowTitle('ACQ4 Console')

        state = self.manager.readConfigFile(self.stateFile)
        # restore window position
        if 'geometry' in state:
            geom = Qt.QRect(*state['geometry'])
            self.win.setGeometry(geom)

        # restore dock configuration
        if 'window' in state:
            ws = Qt.QByteArray.fromPercentEncoding(state['window'].encode())
            self.win.restoreState(ws)

        self.win.show()

    def quit(self):
        print("console quit", self.stateFile)
        ## save ui configuration
        geom = self.win.geometry()
        state = {'window': bytes(self.win.saveState().toPercentEncoding()).decode(), 'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        self.manager.writeConfigFile(state, self.stateFile)
        Module.quit(self)


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
        

