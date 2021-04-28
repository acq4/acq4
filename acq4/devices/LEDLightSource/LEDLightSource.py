# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.devices.LightSource import LightSource


class LEDLightSource(LightSource):
    """Light source device controlled using digital outputs."""
    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)

        self._channelsByName = {}  # name: (dev, chan)
        self._channelNames = {} # (dev, chan): name

        for name, conf in config['leds'].items():
            device, chan = conf.pop("channel")
            dev = dm.getDevice(device)
            dev.sigHoldingChanged.connect(self._mkcb(dev))

            conf['active'] = dev.getChanHolding(chan) > 0
            self.addSource(name, conf)
            self._channelsByName[name] = (dev, chan)
            self._channelNames[(dev, chan)] = name

    def _mkcb(self, dev):
        return lambda chan, val: self._channelStateChanged(dev, chan, val)

    def _channelStateChanged(self, dev, channel, value):
        name = self._channelNames.get((dev, channel), None)
        if name is None:
            return
        state = bool(value)
        if self.sourceConfigs[name]['active'] != state:
            self.sourceConfigs[name]['active'] = state
            self.sigLightChanged.emit(self, name)
            self._updateXkeyLight(name)

    def setSourceActive(self, name, active):
        dev, chan = self._channelsByName[name]
        level = float(active) * self.sourceConfigs[name].get('onValue', 1.0)
        dev.setChanHolding(chan,  level)

