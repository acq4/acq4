import threading

from acq4.modules.Module import Module
from acq4.util.threadrun import inGuiThread
from .gui import VisualizerWindow


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"
    interfaceName = "3D Visualizable"

    win = None

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.isReady = threading.Event()
        self.openWindow()
        self._adapters = {}
        manager.interfaceDir.sigInterfaceListChanged.connect(self.onInterfaceListChanged)
        self.onInterfaceListChanged(self.manager.interfaceDir.typeList)

    @inGuiThread
    def onInterfaceListChanged(self, types: dict):
        for name in types.get(self.interfaceName, []):
            if name not in self._adapters:
                obj = self.manager.getInterface(self.interfaceName, name)
                adapter = obj.visualize3DAdapter(self.win)
                if adapter is not None:
                    self.win.addAdapter(adapter, self.isReady)
                    self._adapters[name] = adapter

    @inGuiThread
    def openWindow(self):
        if self.win is None:
            self.win = VisualizerWindow(len(self.manager.listInterfaces(self.interfaceName)))
        self.win.show()
