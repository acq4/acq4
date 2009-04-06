# -*- coding: utf-8 -*-
from lib.modules.Module import *
from Camera import PVCamera

class Camera(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        camDev = self.config['camDev']
        self.cam = self.manager.getDevice(camDev)
        self.ui = PVCamera(self)
        
    def insertROI(self, roi):
        return handle