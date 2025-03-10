from acq4.modules.Module import Module
from .gui import VisualizerWindow
from acq4.util.threadrun import runInGuiThread


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    win = None

    @classmethod
    def openWindow(cls):
        if cls.win is None:
            cls.win = VisualizerWindow()
        cls.win.show()
        cls.win.clear()

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        runInGuiThread(self.openWindow)
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self.win.addDevice(dev)
