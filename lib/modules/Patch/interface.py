# -*- coding: utf-8 -*-
from lib.modules.Module import *
from Patch import *

class Patch(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = PatchWindow()
    