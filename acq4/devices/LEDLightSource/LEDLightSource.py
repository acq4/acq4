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
        self.lightsourceconfig = config.get('leds')

        self.leds = {}
        self.ledState = []
        self.ledStatus ={}

        for name, conf in self.lightsourceconfig.iteritems():
            chan = conf["channel"][1]
            device = conf["channel"][0]

            dev = dm.getDevice(device)

            dev.sigHoldingChanged.connect(self.updateLEDState)

            self.leds[name] = (dev, conf['channel'])
            #get an inital state
            initState = dev.getChannelValue(chan)

            ledStatusItem = {"name":name, "state": initState, "chan":chan}
            self.ledState.append(ledStatusItem)

        self.sourceState["leds"] = self.ledState

    def updateLEDState(self, channel, value):
        for x in range(len(self.ledState)):
            if (self.ledState[x]["chan"] == channel):
                self.ledState[x]["state"] = value

        self.sourceState["leds"] = self.ledState
        self.sigLightChanged.emit(self.ledState)    

    def getLEDState(self):
        self.sourceState = []
        with self.lock:
            change = {}
            for name, conf in self.leds.iteritems():
                daq, chan = conf
                val = daq.getChannelValue(chan[1], block=False)
                self.ledState[name] = val

                if self.ledState.get(name, None) != val:
                    change[name] = val
                    self.ledState[name] = val

        self.sourceState["leds"] = self.ledState
        

