# -*- coding: utf-8 -*-
from acq4.modules.Module import *
from PatchWindow import *
import os
from PyQt4 import QtGui

class Patch(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = PatchWindow(manager, config)
        self.ui.sigWindowClosed.connect(self.quit)
        mp = os.path.dirname(__file__)
        self.ui.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
    
    def window(self):
        return self.ui

    def quit(self):
        self.ui.quit()
        Module.quit(self)