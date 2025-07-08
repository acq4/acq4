# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.devices.Device import Device


class Trigger(Device):
    """
    A device for triggering DAQ acquisition, such as a foot switch or external trigger.
    
    Configuration options:
    
    * **channels** (dict): Mapping of DAQ device names to trigger channels
        - Key: DAQ device name (e.g., 'DAQ')
        - Value: DAQ channel path (e.g., '/Dev1/PFI5')
    
    Example configuration::
    
        FootSwitch:
            driver: 'Trigger'
            channels:
                DAQ: '/Dev1/PFI5'
    """
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config

    def getTriggerChannels(self, daq: str) -> dict:
        return {'input': self.config['channels'].get(daq, None), 'output': None}

