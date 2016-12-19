# -*- coding: utf-8 -*-
from acq4.devices.Device import *
from acq4.devices.LightSource import *
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTaskGui
from PyQt4 import QtCore, QtGui
import acq4.util.Mutex as Mutex

class LEDLightSource(LightSource):
    """Simple device which reports information of current illumination source."""
    
    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)
        self.config = config
        self.leds = {}
        # print self.config['leds']

        for name, conf in self.config['leds'].iteritems():
            for k, v in conf.iteritems():
                if (k == "channel"):
                    chan = v[1]
                    device = v[0]
                    dev = dm.getDevice(device)

                    self.leds[name] = (dev, conf['channel'])

        self.state = {}

        self.poll()
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(config['interval']*1000)

    def poll(self):
        with self.lock:
            change = {}
            for name, conf in self.leds.iteritems():
                daq, chan = conf
                # print "daq:", daq
                # print "chan:", chan
                val = daq.getChannelValue(chan[1], block=False)
                # print "val:", val
                if val is False: ## device is busy; try again later
                    continue

                if self.state.get(name, None) != val:
                    change[name] = val
                    self.state[name] = val

        if len(change) > 0:
            self.sigLightChanged.emit(self, change)

        global stateToReport
        stateToReport = self.state

def lightSourceStatus():
    return stateToReport
