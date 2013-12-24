# -*- coding: utf-8 -*-
from acq4.devices.Device import *
class Trigger(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config

    def getTriggerChannel(self, daq):
        if daq in self.config:
            return self.config[daq]
        return None
        
