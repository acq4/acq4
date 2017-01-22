# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from PyQt4 import QtCore, QtGui
import acq4.util.Mutex as Mutex

class LightSource(Device):
    """Simple device which reports information of current illumination source."""

    sigLightChanged = QtCore.Signal(object) # to be used upstream 
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lightsourceconfig = config.get('sources', config)
        self.sourceState = {}
        self.lock = Mutex.Mutex()

    def describe(self):
        self.description = []

        for name, conf in self.lightsourceconfig.iteritems():
            if not isinstance(conf, basestring):
                sources = {}
                sources["source"] = name
                sourceDescription = []

                for k, v in conf.iteritems():
                    name = k
                    desc = {}
                    desc['name'] = k

                    for key, value in v.iteritems():
                        desc[key] = value
                        
                    sourceDescription.append(desc)

                sources["description"] = sourceDescription
                self.description.append(sources)

        return self.description	

    def getLightSourceState(self):
        return self.sourceState

    def describeAll(self):
        self.descriptionAll = []

        for name, conf in self.lightsourceconfig.iteritems():
            if not isinstance(conf, basestring):
                sources = {}
                sources = {"source": name}

                for k, v in conf.iteritems():
                    name = k
                    desc = {}
                    desc = {'name':name}

                    for key, value in v.iteritems():
                        desc[key] = value

                sources["description"] = desc
                self.descriptionAll.append(sources)

        return self.descriptionAll

