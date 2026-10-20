from acq4.devices.LightSource import LightSource
from acq4.drivers.ThorlabsDC4100 import ThorlabsDC4100 as DC4100Driver


class ThorlabsDC4100(LightSource):
    """
    Driver for Thorlabs DC4100 4-channel LED driver.
    
    Provides independent control of up to 4 LED channels with brightness control.
    
    Thorlabs DC4100-specific configuration options:
    
    * **port** (str, optional): Serial port for communication
      Uses auto-detection if not specified.
    
    Standard LightSource configuration options (see LightSource base class):
    
    * **sources** (dict): LED channel configurations
        - Key: Source name (arbitrary string)
        - Value: Dict with channel configuration:
            - channel: LED channel number (1-4)
            - wavelength: LED wavelength in meters (auto-detected if not specified)
            - adjustableBrightness: Whether brightness is adjustable (default: True)
            - initialState: State to apply at startup; True/False to turn the LED on/off,
              or a dict with optional 'active' and 'brightness' keys (optional; if omitted,
              the LED is left in whatever state the hardware is already in)
    
    Example configuration::
    
        DC4100:
            driver: 'ThorlabsDC4100'
            port: 'COM5'
            sources:
                Blue:
                    channel: 1
                    wavelength: 470e-9
                    initialState:  # turn this LED on at half brightness at startup
                        active: True
                        brightness: 0.5
                Green:
                    channel: 2  
                    wavelength: 525e-9
                Red:
                    channel: 3
                    wavelength: 625e-9
    """
    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)
        port = config.get('port', None)
        self.dev = DC4100Driver(port=port)
        sources = config.get('sources', {})
        # every source is checked before any of them is built: addSource applies
        # initialState, which switches an LED on, and a device that raises partway
        # through construction is never registered -- its lit LED would be absent
        # from every UI with no object left that could switch it off
        self.validateSourceConfigs(sources)
        for key, sourceConfig in sources.items():
            sourceConfig.setdefault('adjustableBrightness', True)
            chan = sourceConfig['channel']
            sourceConfig.setdefault('wavelength', self.dev.get_wavelength(chan))
            self.addSource(key, sourceConfig)

    def validateSourceConfig(self, name, conf):
        if 'channel' not in conf:
            raise ValueError(f"Light source config ({self}, {name}) must include `channel: N`")
        super().validateSourceConfig(name, conf)

    def setSourceActive(self, source, active):
        chan = self._sourceChannel(source)
        self.dev.set_led_channel_state(chan, active)
        self.sourceConfigs[source]['active'] = active
        self._updateXkeyLight(source)
        self.sigLightChanged.emit(self, source)

    def sourceActive(self, source):
        chan = self._sourceChannel(source)
        return self.dev.get_led_channel_state(chan)

    def setSourceBrightness(self, source, brightness):
        chan = self._sourceChannel(source)
        self.dev.set_brightness(chan, brightness * 100)

    def getSourceBrightness(self, source):
        chan = self._sourceChannel(source)
        return self.dev.get_brightness(chan) / 100

    def _sourceChannel(self, source):
        return self.sourceConfigs[source]['channel']

