# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.devices.Device import *
from acq4.util import Qt
import acq4.util.Mutex as Mutex


class DIOSwitch(Device):
    """Simple device which polls DIO ports on a DAQ and reports when their state changes."""
    
    sigSwitchChanged = Qt.Signal(object, object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex.Mutex()
        self.daqs = {}
        for name, conf in config['channels'].items():
            #daq = conf[0]
            #chan = conf[1]
            dev = dm.getDevice(conf['device'])
            self.daqs[name] = (dev, conf['channel'])
        self.state = {}
        
        self.poll()
        
        self.timer = Qt.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(config['interval']*1000)
        

    def getSwitch(self, name):
        with self.lock:
            return self.state[name]
        
    def poll(self):
        with self.lock:
            change = {}
            for name, conf in self.daqs.items():
                daq, chan = conf
                val = daq.getChannelValue(chan, block=False)
                if val is False: ## device is busy; try again later
                    continue
                        
                if self.state.get(name, None) != val:
                    change[name] = val
                self.state[name] = val
        if len(change) > 0:
            self.sigSwitchChanged.emit(self, change)
            
    def deviceInterface(self, win):
        with self.lock:
            return DevGui(self, self.state)
    
    def quit(self):
        self.timer.stop()
 
class DevGui(Qt.QWidget):
    def __init__(self, dev, state):
        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.labels = {}
        self.dev = dev
        row = 0
        for name in self.dev.state:
            l1 = Qt.QLabel(name)
            l2 = Qt.QLabel()
            self.labels[name] = l2
            self.labels[name+'_name'] = l1
            self.layout.addWidget(l1, row, 0)
            self.layout.addWidget(l2, row, 1)
            row += 1
        self.dev.sigSwitchChanged.connect(self.update)
        self.update(None, state)
        
    def update(self, sw, change):
        for name, val in change.items():
            if val:
                self.labels[name].setText('ON')
            else:
                self.labels[name].setText('OFF')
            
            
            
            