from __future__ import print_function

from acq4.devices.LightSource import LightSource
from acq4.drivers.zeiss import ZeissMtbSdk


class ZeissLamp(LightSource):
    """
    Driver for Zeiss microscope lamps via MTB (Microscopy Technology Base) API.
    
    Controls transmitted light and reflected light lamps on Zeiss microscopes
    with brightness adjustment.
    
    Zeiss-specific configuration options:
    
    * **transOrReflect** (str, optional): Lamp type ('Transmissive' or 'Reflective')
      Default: 'Transmissive'
    
    * **ZeissMtbComponentID** (str, optional): Specific Zeiss component ID
      Overrides transOrReflect if specified
    
    * **apiDllLocation** (str, optional): Path to MTBApi.dll file
      Uses standard location if not specified
    
    Standard LightSource configuration options (see LightSource base class):
    
    * **parentDevice** (str, optional): Name of parent optical device
    
    * **transform** (dict, optional): Spatial transform relative to parent device
    
    Example configuration::
    
        ZeissLamp:
            driver: 'ZeissLamp'
            transOrReflect: 'Transmissive'
            parentDevice: 'Microscope'
    
    or with custom component::
    
        ZeissReflectorLamp:
            driver: 'ZeissLamp'
            ZeissMtbComponentID: 'MTB_RL_LAMP_ID'
            apiDllLocation: 'C:/CustomPath/MTBApi.dll'
    """
    TRANSMISSIVE = "Transmissive"
    REFLECTIVE = "Reflective"

    def __init__(self, dm, config, name):
        super(ZeissLamp, self).__init__(dm, config, name)
        self._zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config.get("ZeissMtbComponentID") is not None:
            self._lamp = self._zeiss.getComponentByID(config["ZeissMtbComponentID"])
        elif config.get("transOrReflect") == ZeissLamp.REFLECTIVE:
            self._lamp = self._zeiss.getRLLamp()
        else:
            self._lamp = self._zeiss.getTLLamp()

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
