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

        # First, define a DAQGeneric device with digital output channels for controlling the LEDs:
        # (this tells ACQ4 which DAQ lines are used to access the LEDs)
        LEDChannels:
            driver: 'DAQGeneric'
            channels:
                Blue:
                    device: 'DAQ'  # note that DAQ must have been defined previously; see the NiDAQ device
                    channel: '/Dev1/port0/line2'
                    type: 'do'
                Green:
                    device: 'DAQ'
                    channel: '/Dev1/port0/line3'
                    type: 'do'

        # Then define the LED light source device, referencing the DAQ channels:
        # (this tells ACQ4 about the LEDs themselves)
        LEDArray:
            driver: 'LEDLightSource'
            parentDevice: 'Microscope'  # optionally, specify that these LEDs are attached to a microscope device
            sources:
                Blue:
                    channel: ['LEDChannels', 'Blue']
                    wavelength: 470 * nm
                    onValue: 1  # digital output is 1 when LED is on
                Green:
                    channel: ['LEDChannels', 'Green']
                    wavelength: 525 * nm
                    onValue: 1  # digital output is 1 when LED is on

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
