from acq4.devices.OdorDelivery import OdorDelivery
from acq4.drivers.Acces.UsbDIO96 import UsbDIO96, DEFAULT_SINGLE_DEVICE_ID


class AccesOdorDelivery(OdorDelivery):
    def __init__(self, deviceManager, config: dict, name: str):
        super().__init__(deviceManager, config, name)

        self._dev = UsbDIO96(config.get("deviceId", DEFAULT_SINGLE_DEVICE_ID))
        self._dev.configure_channels(UsbDIO96.OUTPUT, self.odorChannels())
        self._triggerReadChannel = config.get("triggerReadChannel", 11)
        # MC: leaving this off for now; we may get good enough synchronicity without it
        # self._daqTriggerChannel = config.get("daqTriggerChannel")  # TODO default? format?

    def setChannelValue(self, channel: int, value: int):
        self._dev.write(channel, value)
