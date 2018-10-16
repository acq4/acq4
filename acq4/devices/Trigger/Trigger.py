# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.devices.Device import *
class Trigger(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config

    def getTriggerChannel(self, daq):
        if daq in self.config['channels']:
            return self.config['channels'][daq]
        return None
        
