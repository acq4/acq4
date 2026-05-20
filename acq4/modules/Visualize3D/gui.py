import os
from typing import Callable

import pyqtgraph as pg
from acq4.util import Qt
from pyqtgraph import opengl as gl
from pyqtgraph.parametertree import Parameter, ParameterTree


class VisualizerWindow(Qt.QMainWindow):
    focusEvent = Qt.pyqtSignal()

    def __init__(self, expectedAdapters=0, testing=False):
        super().__init__(None)
        self.testing = testing
        self._adaptersBeingAdded = expectedAdapters
        self._adapters = []
        self._moduleReadyEvent = None

        self.setWindowTitle("3D Visualization of all Optomech Devices")
        self.setGeometry(50, 50, 1000, 600)
        self.setWindowIcon(
            Qt.QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons.svg"))
        )

        # Main layout is a horizontal splitter
        self.splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        self.setCentralWidget(self.splitter)

        # Left side: 3D view
        self.viewWidget = Qt.QWidget()
        self.viewLayout = Qt.QVBoxLayout()
        self.viewWidget.setLayout(self.viewLayout)
        self.splitter.addWidget(self.viewWidget)

        # Create 3D view
        self.view = gl.GLViewWidget()
        self.viewLayout.addWidget(self.view)
        self.view.setCameraPosition(distance=0.2, azimuth=-90, elevation=30)
        grid = gl.GLGridItem()
        grid.scale(0.001, 0.001, 0.001)
        self.view.addItem(grid)
        axes = gl.GLAxisItem()
        axes.setSize(0.1, 0.1, 0.1)
        self.view.addItem(axes)

        # Right side: ParameterTree for all device controls
        self._rootParam = Parameter.create(name='devices', type='group', children=[])
        self.paramTree = ParameterTree()
        self.paramTree.setParameters(self._rootParam, showTop=False)
        self.splitter.addWidget(self.paramTree)

        # Set splitter sizes
        self.splitter.setSizes([700, 300])

        # Connect signals
        self.focusEvent.connect(self._focus)

    def addControls(self, param: Parameter):
        self._rootParam.addChild(param)

    def removeControls(self, param: Parameter):
        self._rootParam.removeChild(param)

    def add3DItem(self, item):
        self.view.addItem(item)

    def remove3DItem(self, item):
        self.view.removeItem(item)

    def target(self, visible=False, color=(0, 0, 1, 1)):
        target = gl.GLScatterPlotItem(pos=[], color=color, size=10, pxMode=True)
        target.setVisible(visible)
        self.view.addItem(target)
        return target

    def path(self, color, visible=False):
        path = gl.GLLinePlotItem(pos=[], color=color, width=1)
        path.setVisible(visible)
        self.view.addItem(path)
        return path

    def centerOnPosition(self, pos: tuple[float, float, float]) -> None:
        """Center the 3D camera on the given (x, y, z) position."""
        self.view.setCameraPosition(pos=pg.Vector(*pos))

    def focus(self):
        self.focusEvent.emit()

    def _focus(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def addAdapter(self, adapter, ready_event=None):
        try:
            self._moduleReadyEvent = ready_event
            self._adapters.append(adapter)
        finally:
            self._adaptersBeingAdded -= 1
            if self._moduleReadyEvent is not None and self._adaptersBeingAdded == 0:
                self._moduleReadyEvent.set()
                self._moduleReadyEvent = None

    def removeAdapter(self, adapter):
        if adapter in self._adapters:
            self._adapters.remove(adapter)
            adapter.clear()

    def findAdapter(self, test: Callable):
        for adapter in self._adapters:
            if test(adapter):
                return adapter
        return None
