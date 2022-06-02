# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.devices.Device import Device


class Trigger(Device):
    """A device only used to trigger a DAQ; for example, a foot switch.
    """
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config

    def getTriggerChannels(self, daq: str) -> dict:
        return {'input': self.config['channels'].get(daq, None), 'output': None}

