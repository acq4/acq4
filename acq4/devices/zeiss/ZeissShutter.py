from pyqtgraph.util.mutex import Mutex

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

    sigShutterStateChanged = Qt.Signal(bool)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self._zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config.get("ZeissMtbComponentID", None) is not None:
            self._shutter = self._zeiss.getSpecificShutter(config["ZeissMtbComponentID"])
        elif config.get("transOrReflect") == self.REFLECTIVE:
            self._shutter = self._zeiss.getRLShutter()
        else:
            self._shutter = self._zeiss.getTLShutter()
        self._shutter = self._zeiss.getShutter()
        self._shutter.registerEventHandlers(onSettle=self.shutterStateSettled)

    def shutterStateSettled(self, position):
        self.sigShutterStatewitchChanged.emit(position)

    def setIsOpen(self, isOpen):
        self._shutter.setIsOpen(isOpen)

    def getIsOpen(self):
        return self._shutter.getIsOpen()

    def disconnect(self):
        self._zeiss.disconnect()

    def deviceInterface(self, win):
        return ShutterDevGui(self)

    def taskInterface(self, taskRunner):
        return ShutterTaskGui(self, taskRunner)


class ShutterDevGui(Qt.QWidget):
    def __init__(self, dev):
        super(ShutterDevGui, self).__init__()
        name = dev.getName()
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)
        btn = Qt.QPushButton(name)
        btn.setCheckable(True)
        self.sourceActivationButtons[name] = btn
        self.layout.addWidget(btn, 0, 0)
        btn.clicked.connect(lambda isOpen: self.dev.setIsOpen(isOpen))
        self.onDevChange()

    def onDevChange(self):
        pass  # TODO


class ShutterTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        super(ShutterTaskGui, self).__init__(dev, taskRunner)
        self.dev = dev
        self.taskRunner = taskRunner
        # TODO?
