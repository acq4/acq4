from acq4.devices.PressureControl import PressureControl


class MockPressureControl(PressureControl):
    """
    Simulated pressure control device for testing and demonstration.
    
    Provides the same interface as real pressure controllers but without hardware.
    Useful for developing and testing experiments without physical devices.
    
    Configuration options (see PressureControl base class):
    
    * **maximum** (float, optional): Maximum pressure limit in Pa
    
    * **minimum** (float, optional): Minimum pressure limit in Pa
    
    * **regulatorSettlingTime** (float, optional): Time for pressure to settle
    
    Example configuration::
    
        MockPressure:
            driver: 'MockPressureControl'
            maximum: 50 * kPa
            minimum: -50 * kPa
            regulatorSettlingTime: 0.3 * s
    """
    def __init__(self, manager, config, name):
        super().__init__(manager, config, name)
        self.pressure = 0

    def _setPressure(self, p):
        self.pressure = p

    def getPressure(self):
        return getattr(self, "pressure", 10)

    def _setSource(self, source):
        self.source = source

    def getSource(self):
        return getattr(self, "source", self.sources[0])
