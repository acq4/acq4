# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from acq4.devices.OptomechDevice import OptomechDevice

class PhotoDetector(DAQGeneric, OptomechDevice):
    def __init__(self, dm, config, name):
        print 'PMT configure'
        omConf = {}
        for k in ['parentDevice', 'transform']:
            if k in config:
                omConf[k] = config.pop(k)
        OptomechDevice.__init__(self, dm, config, name)
        DAQGeneric.__init__(self, dm, config, name)

    def getFilterDevice(self):
        # return parent filter device or None
        
        
