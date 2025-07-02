from acq4.devices.Device import Device, TaskGui
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt


class ZeissShutter(Device):
    """
    Driver for Zeiss microscope shutters via MTB (Microscopy Technology Base) API.
    
    Controls transmitted light and reflected light shutters on Zeiss microscopes.
    
    Configuration options:
    
    * **transOrReflect** (str, optional): Shutter type ('Transmissive' or 'Reflective')
      Default: 'Transmissive'
    
    * **ZeissMtbComponentID** (str, optional): Specific Zeiss component ID
      Overrides transOrReflect if specified
    
    * **apiDllLocation** (str, optional): Path to MTBApi.dll file
      Uses standard location if not specified
    
    Emits sigShutterStateChanged(isOpen) when shutter state changes.
    
    Example configuration::
    
        ZeissShutter:
            driver: 'ZeissShutter'
            transOrReflect: 'Transmissive'
    
    or with custom component::
    
        ZeissRLShutter:
            driver: 'ZeissShutter'
            ZeissMtbComponentID: 'MTB_RL_SHUTTER_ID'
            apiDllLocation: 'C:/CustomPath/MTBApi.dll'
    """
    TRANSMISSIVE = "Transmissive"
    REFLECTIVE = "Reflective"

    sigShutterStateChanged = Qt.Signal(object)  # (isOpen)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self._zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config.get("ZeissMtbComponentID", None) is not None:
            self._shutter = self._zeiss.getSpecificShutter(config["ZeissMtbComponentID"])
        elif config.get("transOrReflect") == self.REFLECTIVE:
            self._shutter = self._zeiss.getRLShutter()
        else:
            self._shutter = self._zeiss.getTLShutter()
        self._shutter.registerEventHandlers(
            onSettle=lambda isOpen: self.sigShutterStateChanged.emit(isOpen))

    def setIsOpen(self, isOpen):
        self._shutter.setIsOpen(isOpen)

    def getIsOpen(self):
        return self._shutter.getIsOpen()

    def disconnect(self):
        self._zeiss.disconnect()

    def getName(self):
        return self._shutter.getName()

    def deviceInterface(self, win):
        return ShutterDevGui(self)

    def taskInterface(self, taskRunner):
        return None  # TODO


class ShutterDevGui(Qt.QWidget):
    def __init__(self, dev):
        """
        Parameters
        ----------
        dev : ZeissShutter
        """
        super(ShutterDevGui, self).__init__()
        self.dev = dev
        name = dev.getName()
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.btn = Qt.QPushButton(name)
        self.btn.setCheckable(True)
        self.layout.addWidget(self.btn, 0, 0)
        self.btn.clicked.connect(self.dev.setIsOpen)
        self._noticeDevChange(self.dev.getIsOpen())
        self.dev.sigShutterStateChanged.connect(self._noticeDevChange)

    def _noticeDevChange(self, isOpen):
        self.btn.setChecked(isOpen)


class ShutterTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        super(ShutterTaskGui, self).__init__(dev, taskRunner)
        self.dev = dev
        self.taskRunner = taskRunner
        # TODO?
