# -*- coding: utf-8 -*-
from lib.devices.Device import Device

class testdev(Device):
    """Test device."""
    def __init__(self, config):
        Device.__init__(self, config)
        self.conf = config
    
    def prepareProtocol(cmd, tasks):
        ## create channels, configure scaling.
        ## return command waveforms (or None if waveforms are unchanged) and metaData for output array
        
        raise Exception("Function prepareProtocol() not defined in subclass!")
        
    def setHolding(self):
        """set all channels for this device to their configured holding level"""
        pass
