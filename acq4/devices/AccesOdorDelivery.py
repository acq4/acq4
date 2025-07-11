from acq4.devices.OdorDelivery import OdorDelivery
from acq4.drivers.Acces.UsbDIO96 import UsbDIO96, DEFAULT_SINGLE_DEVICE_ID


class AccesOdorDelivery(OdorDelivery):
    """
    Odor delivery system using ACCES I/O USB-DIO-96 digital I/O device.
    
    Controls solenoid valves for precise odor stimulus delivery via digital outputs.
    
    ACCES-specific configuration options:
    
    * **deviceId** (int, optional): USB-DIO-96 device ID 
      Uses default single device ID if not specified
    
    * **triggerReadChannel** (int, optional): Channel for trigger signal reading 
      (default: 11)
    
    Standard OdorDelivery configuration options (see OdorDelivery base class):
    
    * **odors** (dict): Odor channel mappings
        - Key: Odor name
        - Value: Digital output channel number
    
    Example configuration::
    
        OdorDelivery:
            driver: 'AccesOdorDelivery'
            deviceId: 0
            triggerReadChannel: 11
            odors:
                banana: 0
                apple: 1
                vanilla: 2
    """
    def __init__(self, deviceManager, config: dict, name: str):
        super().__init__(deviceManager, config, name)

        self._dev = UsbDIO96(config.get("deviceId", DEFAULT_SINGLE_DEVICE_ID))
        self._dev.configure_channels(UsbDIO96.OUTPUT, self.odorChannels())
        self._triggerReadChannel = config.get("triggerReadChannel", 11)
        # MC: leaving this off for now; we may get good enough synchronicity without it
        # self._daqTriggerChannel = config.get("daqTriggerChannel")  # TODO default? format?

    def setChannelValue(self, channel: int, value: int):
        self._dev.write(channel, value)
