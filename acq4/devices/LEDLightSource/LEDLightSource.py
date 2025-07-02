from acq4.devices.LightSource import LightSource


class LEDLightSource(LightSource):
    """
    Light source device controlled via DAQ digital/analog outputs.
    
    Controls LED arrays or other light sources using DAQ output channels
    with configurable on/off values.
    
    Configuration options:
    
    * **sources** (dict) or **leds** (dict): Light source definitions
        - Key: Source name
        - Value: Source configuration dict:
            - channel: [device_name, channel_path] for DAQ output
            - onValue: Output value for "on" state (default: 1.0)
            - wavelength: LED wavelength in meters (optional)
            - adjustableBrightness: Whether brightness is adjustable (default: False)
    
    Standard LightSource configuration options (see LightSource base class):
    
    * **parentDevice** (str, optional): Name of parent optical device
    
    * **transform** (dict, optional): Spatial transform relative to parent device
    
    Example configuration::
    
        LEDArray:
            driver: 'LEDLightSource'
            parentDevice: 'Microscope'
            sources:
                Blue:
                    channel: ['DAQ', '/Dev1/port0/line0']
                    wavelength: 470e-9
                    onValue: 5.0
                Green:
                    channel: ['DAQ', '/Dev1/port0/line1'] 
                    wavelength: 525e-9
                    onValue: 3.3
    """

    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)

        self._channelsByName = {}  # name: (dev, chan)
        self._channelNames = {}  # (dev, chan): name

        for name, conf in config.get('sources', config.get('leds', {})).items():
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
        dev.setChanHolding(chan, level)
