from acq4.devices.Device import Device, TaskGui
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt


class ZeissShutter(Device):
    """
    Config Options
    --------------
    transOrReflect : str
        "Transmissive" | "Reflective" Which of the two standard shutters to represent.
        (Defaults to "Transmissive")
    ZeissMtbComponentID : str
        If pointing to a different Zeiss component, this overrides `transOrReflect`.
    apiDllLocation : str
        The path for the MTBApi.dll file, if non-standard.
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
