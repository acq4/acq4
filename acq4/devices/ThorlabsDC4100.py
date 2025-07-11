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
    
    Example configuration::
    
        DC4100:
            driver: 'ThorlabsDC4100'
            port: 'COM5'
            sources:
                Blue:
                    channel: 1
                    wavelength: 470e-9
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
        for key,sourceConfig in config.get('sources', {}).items():
            if 'channel' not in sourceConfig:
                raise ValueError(f"Light source config ({self}, {key}) must include `channel: N`")
            sourceConfig.setdefault('adjustableBrightness', True)
            chan = sourceConfig['channel']
            sourceConfig.setdefault('wavelength', self.dev.get_wavelength(chan))
            self.addSource(key, sourceConfig)

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

