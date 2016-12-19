# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from PyQt4 import QtCore, QtGui
import acq4.util.Mutex as Mutex


class LightSource(Device):
    """Simple device which reports information of current illumination source."""

    sigLightChanged = QtCore.Signal(object, object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config.get('leds', config)
        self.lock = Mutex.Mutex()
        # LEDLightSource.__init(self, dm, config, name)

    def describe(self, params=None):
 		self.description = []
 		for source in config:
 			for items in config[source]:
 					for illum in self.lightSourceList:
 						if (illum['state'] == True):
 							desc = {'name': config[source]['name'], 'model': config[source]['model'], 'wavelength':config[source]['power']}
        	self.description.append(desc)

		return self.description	

	# def describeAll(self, params=None):
	# 	self.descriptionAll = []
	# 	for source in config:
	# 		for items in config[source]:
	# 			desc = {'name': config[source]['name'], 'model': config[source]['model'], 'wavelength':config[source]['power']}
	# 		self.description.append(desc)
	# 	return self.descriptionAll