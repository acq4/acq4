# -*- coding: utf-8 -*-
from acq4.modules.Module import *
from PatchWindow import *
import os
from PyQt4 import QtGui
from collections import OrderedDict


class Patch(Module):

    defaults = {
        'mode': 'vc',
        'rate': 40000,
        'downsample': 1,
        'cycleTime': .2,
        'recordTime': 0.1,
        'delayTime': 0.01,
        'pulseTime': 0.01,
        'icPulse': -30e-12,
        'vcPulse': -10e-3,
        'icHolding': 0,
        'vcHolding': -60e-3,
        'icHoldingEnabled': False,
        'icPulseEnabled': True,
        'vcHoldingEnabled': False,
        'vcPulseEnabled': True,
        'drawFit': True,
        'average': 1,
        }

    defaultModes = OrderedDict([
        ('Bath', dict(
            mode='vc',
            vcPulseEnabled=True, 
            vcHoldingEnabled=False,
            cycleTime=0.2,
            pulseTime=10e-3,
            delayTime=10e-3,
            average=1
            )),
        ('Patch', dict(
            mode='vc',
            vcPulseEnabled=True, 
            vcHoldingEnabled=True,
            cycleTime=0.2,
            pulseTime=10e-3,
            delayTime=10e-3,
            average=1
            )),
        ('Cell', dict(
            mode='ic',
            vcPulseEnabled=True, 
            cycleTime=250e-3,
            pulseTime=150e-3,
            delayTime=30e-3,
            average=1
            )),
        ('Monitor', dict(
            cycleTime=40,
            average=5
            )),
        ])
    
    def monitorMode(self):
        self.ui.cycleTimeSpin.setValue(40)
        self.ui.averageSpin.setValue(5)
    
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        
        # Read mode configurations from config file
        modes = config.get('modes', self.defaultModes)
        self.defaults.update(modes.get('default', {}))
        modes['default'] = self.defaults
        
        for modeName, mode in modes.items():
            for param, val in mode.items():
                if param not in self.defaults:
                    print 'Ignoring unknown parameter in config file: "%s".' % param
                    continue
                typ = type(self.defaults[param])
                if not isinstance(val, typ) and not (typ == float and isinstance(val, int)):
                    print "Warning: Value for parameter '%s' should have type %s." % (param, typ) 
                    continue
        
        self.ui = PatchWindow(manager, config['clampDev'], modes)
        display = config.get('display', {})
        for param, val in display.items():
            self.ui.changeDisplay(param, val)

        self.ui.sigWindowClosed.connect(self.quit)
        mp = os.path.dirname(__file__)
        self.ui.setWindowIcon(QtGui.QIcon(os.path.join(mp, 'icon.png')))
    
    def window(self):
        return self.ui

    def quit(self):
        self.ui.quit()
        Module.quit(self)
