import threading

from acq4.modules.Module import Module
from acq4.util.threadrun import inGuiThread
from .gui import VisualizerWindow


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    win = None

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.isReady = threading.Event()
        self.openWindow(blocking=True)
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self.win.addDevice(dev, self.isReady)

    @inGuiThread
    def openWindow(self):
        if self.win is None:
            self.win = VisualizerWindow(len(self.manager.listInterfaces("OptomechDevice")))
        self.win.show()
        self.win.clear()
