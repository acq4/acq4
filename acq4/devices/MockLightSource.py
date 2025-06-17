from acq4.devices.LightSource import LightSource


class MockLightSource(LightSource):
    """
    Simulated light source device for testing and demonstration.
    
    Configuration options (see LightSource base class):
    
    * **sources** (dict): Light source definitions
        - Key: Source name (any key except 'driver' and 'parentDevice')
        - Value: Source configuration dict
    
    * **parentDevice** (str, optional): Name of parent optical device
    
    Example configuration::
    
        MockLightSource:
            driver: 'MockLightSource'
            Blue:
                wavelength: 470e-9
                adjustableBrightness: True
            Green:
                wavelength: 525e-9
                adjustableBrightness: True
    """
    def __init__(self, dm, config, name):
        super().__init__(dm, config, name)
        for key in config:
            if key.lower() in ("driver", "parentdevice"):
                continue
            self.addSource(key, config[key])

    def setSourceActive(self, name, active):
        self.sourceConfigs[name]["active"] = active
        self.sigLightChanged.emit(self, name)

    def getSourceBrightness(self, name):
        return self.sourceConfigs[name].get("brightness", 1.0)

    def setSourceBrightness(self, name, value):
        self.sourceConfigs[name]["brightness"] = value
