# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.modules.Module import *
from .PatchWindow import *
import os
from acq4.util import Qt

class Patch(Module):
    moduleDisplayName = "Patch"
    moduleCategory = "Acquisition"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = PatchWindow(manager, config)
        self.ui.sigWindowClosed.connect(self.quit)
        mp = os.path.dirname(__file__)
        self.ui.setWindowIcon(Qt.QIcon(os.path.join(mp, 'icon.png')))
    
    def window(self):
        return self.ui

    def quit(self):
        self.ui.quit()
        Module.quit(self)