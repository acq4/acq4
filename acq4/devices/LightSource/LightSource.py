# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from PyQt4 import QtCore, QtGui
import acq4.util.Mutex as Mutex


class LightSource(Device):
    """Simple device which reports information of current illumination source."""

    sigLightChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lightsourceconfig = config.get('sources', config)

        self.sourceState = {}
        self.lock = Mutex.Mutex()
        self.sigLightChanged.connect(self.lightChanged)


    def describe(self):
        self.description = []

        for name, conf in self.lightsourceconfig.iteritems():
            if (name=="leds"):
                for k, v in conf.iteritems():
                    name = k
                    desc = {'name':name}

                    for key, value in v.iteritems():

                        if (key == "channel"):
                            ledtype = value[1]
                            desc['ledtype'] = ledtype

                        if (key == "model"):
                            model = value
                            desc['model'] = model

                        if (key == "wavelength"):
                            wavelength = value
                            desc['wavelength'] = wavelength

                        if (key == "power"):
                            power = value
                            desc['power'] = power

                    if (self.sourceState[name] == 1):
                        desc['state'] = 1
                        self.description.append(desc)

        return self.description	


    def lightChanged(self, state):
        self.sourceState = state

    def getLightSourceState(self):
        self.getLEDState()
        return self.sourceState

    def describeAll(self):
        self.descriptionAll = []

        for name, conf in self.lightsourceconfig.iteritems():
            if (name=="leds"):
                for k, v in conf.iteritems():
                    name = k
                    desc = {'name':name}

                    for key, value in v.iteritems():
                        if (key == "channel"):
                            ledtype = value[1]
                            desc['ledtype'] = ledtype

                        if (key == "model"):
                            model = value
                            desc['model'] = model

                        if (key == "wavelength"):
                            wavelength = value
                            desc['wavelength'] = wavelength

                        if (key == "power"):
                            power = value
                            desc['power'] = power

                        desc['state'] = 1

                        self.descriptionAll.append(desc)

        return self.descriptionAll

