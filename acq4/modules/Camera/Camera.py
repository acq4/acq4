# -*- coding: utf-8 -*-
from acq4.modules.Module import *
from CameraWindow import CameraWindow
import os
from PyQt4 import QtGui

class Camera(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = CameraWindow(self)
        mp = os.path.dirname(__file__)
        self.ui.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
        manager.declareInterface(name, ['cameraModule'], self)
        
    def window(self):
        return self.ui
        
    def quit(self, fromUi=False):
        if not fromUi:
            self.ui.quit()
        Module.quit(self)
        
    def insertROI(self, roi):
        return handle
