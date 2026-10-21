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
                initialState:  # on at half brightness when acq4 starts
                    active: True
                    brightness: 0.5
            Green:
                wavelength: 525e-9
                adjustableBrightness: True
    """
    def __init__(self, dm, config, name):
        super().__init__(dm, config, name)
        sources = {
            key: conf for key, conf in config.items()
            if key.lower() not in ("driver", "parentdevice")
        }
        # validate every source before adding any; see LightSource.validateSourceConfig
        self.validateSourceConfigs(sources)
        for key, conf in sources.items():
            self.addSource(key, conf)

    def setSourceActive(self, name, active):
        self.sourceConfigs[name]["active"] = active
        self.sigLightChanged.emit(self, name)

    def getSourceBrightness(self, name):
        return self.sourceConfigs[name].get("brightness", 1.0)

    def setSourceBrightness(self, name, value):
        self.sourceConfigs[name]["brightness"] = value
        self.sigLightChanged.emit(self, name)
