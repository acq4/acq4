from __future__ import print_function

from acq4.devices.LightSource import LightSource
from acq4.drivers.zeiss import ZeissMtbSdk


class ZeissLamp(LightSource):
    TRANSMISSIVE = "Transmissive"
    REFLECTIVE = "Reflective"

    def __init__(self, dm, config, name):
        super(ZeissLamp, self).__init__(dm, config, name)
        self._zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config["transOrReflect"] == ZeissLamp.TRANSMISSIVE:
            self._lamp = self._zeiss.getTLLamp()
        else:
            self._lamp = self._zeiss.getRLLamp()

        self.addSource(self._lamp.getID(), {"adjustableBrightness": True})
        self._lamp.registerEventHandlers(
            onChange=self._noticeLightChange,
            onSettle=self._noticeLightChange)

    def _noticeLightChange(self, newValue):
        self.sigLightChanged.emit(self, self._lamp.getID())

    def sourceActive(self, name):
        return self._lamp.getIsActive()

    def setSourceActive(self, name, active):
        self._lamp.setIsActive(active)

    def getSourceBrightness(self, name):
        return (self._lamp.getBrightness() or 0.0) / 100.

    def setSourceBrightness(self, name, percent):
        self._lamp.setBrightness(percent * 100.)
