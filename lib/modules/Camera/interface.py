# -*- coding: utf-8 -*-
from lib.modules.Module import *
from Camera import QtCam

class Camera(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        camDev = self.config['camera']
        self.cam = self.manager.getDevice(camDev)
        self.ui = QtCam(self)
        
    def insertROI(self, roi):
        return handle