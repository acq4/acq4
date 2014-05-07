# -*- coding: utf-8 -*-
from acq4.modules.Module import *
from PatchWindow import *
import os
from PyQt4 import QtGui



class Patch(Module):
    valid_params = {
            'mode': str,
            'rate': float,
            'downsample': int,
            'cycleTime': float,
            'recordTime': float,
            'delayTime': float,
            'pulseTime': float,
            'icPulse': float,
            'vcPulse': float,
            'icHolding': float,
            'vcHolding': float,
            'icHoldingEnabled': bool,
            'icPulseEnabled': bool,
            'vcHoldingEnabled': bool,
            'vcPulseEnabled': bool,
            'drawFit': bool,
            'average': int,
    }

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = PatchWindow(manager, config['clampDev'])
        self.ui.sigWindowClosed.connect(self.quit)
        mp = os.path.dirname(__file__)
        self.ui.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
        
        # Changing defaults using config file
        for param, val in config.items():
            if param == 'clampDev':
                continue
            if not self.valid_params.has_key(param):
                # should probably use showMessage instead of print
                print 'Ignoring unknown parameter in config file: "%s".'%param
                continue
            try:
                self.ui.params[param]=self.valid_params[param](val)
            except:
                print 'Error while setting "%s". Expect a %s, got: "%s" (%s).'%(param, 
                                                                              self.valid_params[param].__name__,
                                                                              val, 
                                                                              type(val).__name__)
                print 'Default value will be used.'
    
    def window(self):
        return self.ui

    def quit(self):
        self.ui.quit()
        Module.quit(self)