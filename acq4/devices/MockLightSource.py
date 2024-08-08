from acq4.devices.LightSource import LightSource


class MockLightSource(LightSource):
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
