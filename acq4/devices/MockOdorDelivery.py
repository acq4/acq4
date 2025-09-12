from acq4.devices.OdorDelivery import OdorDelivery


class MockOdorDelivery(OdorDelivery):
    """
    Simulated odor delivery device for testing and demonstration.
    
    Prints channel operations to console instead of controlling hardware.
    Useful for developing and testing experiments without physical devices.
    
    Configuration options (see OdorDelivery base class):
    
    * **odors** (dict): Odor channel mappings
        - Key: Odor name
        - Value: Channel number
    
    Example configuration::
    
        MockOdorDelivery:
            driver: 'MockOdorDelivery'
            odors:
                banana: 0
                apple: 1
                vanilla: 2
    """
    def setChannelValue(self, channel: int, value: int):
        print(f"{self!r} setting {channel} to {value}")
