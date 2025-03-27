from acq4.devices.LightSource import LightSource
from acq4.drivers.ThorlabsDC4100 import ThorlabsDC4100 as DC4100Driver


class ThorlabsDC4100(LightSource):
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

