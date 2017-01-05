# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from acq4.devices.LightSource import *
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTaskGui
from PyQt4 import QtCore, QtGui
import acq4.util.Mutex as Mutex

class LEDLightSource(LightSource):
    """Simple device which reports the status of the LED Light Sources...reports up to the LightSource object."""
    
    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)
        self.ledconfig = config.get('leds', config)

        self.leds = {}

        for name, conf in self.ledconfig.iteritems():
            for k, v in conf.iteritems():
                if (k == "channel"):
                    chan = v[1]
                    device = v[0]
                    dev = dm.getDevice(device)

                    self.leds[name] = (dev, conf['channel'])

        self.state = {}

    def getLEDState(self):
        with self.lock:
            change = {}
            for name, conf in self.leds.iteritems():
                daq, chan = conf
                val = daq.getChannelValue(chan[1], block=False)
                if val is False: ## device is busy; try again later
                    continue

                if self.state.get(name, None) != val:
                    change[name] = val
                    self.state[name] = val

        if len(change) > 0:
            self.sigLightChanged.emit(self.state)

