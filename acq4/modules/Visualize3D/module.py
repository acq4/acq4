import threading

from acq4.modules.Module import Module
from acq4.util.threadrun import inGuiThread
from .gui import VisualizerWindow


class Visualize3D(Module):
    moduleDisplayName = "Visualize3D"
    moduleCategory = "Utilities"
    interfaceName = "3D Visualizable"

    win = None

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.isReady = threading.Event()
        self.openWindow()
        self._adapters = {}
        manager.interfaceDir.sigInterfaceListChanged.connect(self.onInterfaceListChanged)
        self.onInterfaceListChanged([self.interfaceName])

    @inGuiThread
    def onInterfaceListChanged(self, types: list):
        if self.interfaceName in types:
            seen = set()
            for name in self.manager.listInterfaces(self.interfaceName):
                seen.add(name)
                if name not in self._adapters:
                    obj = self.manager.getInterface(self.interfaceName, name)
                    adapter = obj.visualize3DAdapter(self.win)
                    if adapter is not None:
                        self.win.addAdapter(adapter, self.isReady)
                        self._adapters[name] = adapter
            for name in list(self._adapters.keys()):
                if name not in seen:
                    self.win.removeAdapter(self._adapters[name])
                    del self._adapters[name]

    @inGuiThread
    def openWindow(self):
        if self.win is None:
            self.win = VisualizerWindow(len(self.manager.listInterfaces(self.interfaceName)))
        self.win.show()
