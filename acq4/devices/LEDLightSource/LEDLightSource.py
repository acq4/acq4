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
        self.ledconfig = config.get('leds')

        self.leds = {}
        self.ledState = {}
        self.ledStatus ={}

        for name, conf in self.ledconfig.iteritems():
            chan = conf["channel"][1]
            device = conf["channel"][0]

            dev = dm.getDevice(device)

            dev.sigHoldingChanged.connect(self.updateLEDState)

            self.leds[name] = (dev, conf['channel'])

            ledStatusItem = {"name":name, "state": 0}
            self.ledState[chan] = ledStatusItem

    def updateLEDState(self, channel, value):
        self.ledState[channel]["state"] = value

        self.sourceState["led"] = self.ledState
    


    def getLEDState(self):
        with self.lock:
            change = {}
            for name, conf in self.leds.iteritems():
                daq, chan = conf
                val = daq.getChannelValue(chan[1], block=False)
                self.ledState[name] = val

                if self.ledState.get(name, None) != val:
                    change[name] = val
                    self.ledState[name] = val

        self.sourceState["led"] = self.ledState
        

