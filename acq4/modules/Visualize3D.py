import os
import queue
import time
from threading import Thread

import numpy as np

import pyqtgraph as pg
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.geometry import Plane, Volume
from acq4.util.threadrun import runInGuiThread
from coorx import Transform, SRT3DTransform
from pyqtgraph import opengl as gl
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    win = None

    @classmethod
    def openWindow(cls):
        if cls.win is None:
            cls.win = MainWindow()
        cls.win.clear()
        cls.win.show()

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.gridlines = None
        self.truncated_cone = None
        runInGuiThread(self.openWindow)
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self.win.addDevice(dev)


class MainWindow(Qt.QMainWindow):
    pathStartSignal = Qt.pyqtSignal(object, object, float, list)
    newObstacleSignal = Qt.pyqtSignal(object, object)
    newDeviceSignal = Qt.pyqtSignal(object)
    pathUpdateSignal = Qt.pyqtSignal(object, int)
    focusEvent = Qt.pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("3D Visualization of all Optomech Devices")
        self.setGeometry(50, 50, 800, 600)
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), "icons.svg")))

        self.view = gl.GLViewWidget()
        self.setCentralWidget(self.view)
        self.view.setCameraPosition(distance=0.2, azimuth=-90, elevation=30)
        grid = gl.GLGridItem()
        grid.scale(0.001, 0.001, 0.001)
        self.view.addItem(grid)
        axes = gl.GLAxisItem()
        axes.setSize(0.1, 0.1, 0.1)
        self.view.addItem(axes)
        self.pathStartSignal.connect(self._startPath)
        self.newObstacleSignal.connect(self._addObstacleVolumeOutline)
        self.newDeviceSignal.connect(self._addDevice)
        self.pathUpdateSignal.connect(self._updatePath)
        self.focusEvent.connect(self._focus)
        self._pathUpdates = queue.Queue()
        self._pathWatcherThread = Thread(target=self._watchForPathUpdates)
        self._pathWatcherThread.start()

        self._geometries = {}
        self._path: dict[object, GLGraphicsItem] = {}

    def clear(self):
        for dev in self._geometries:
            self._removeDevice(dev)
        self._geometries = {}
        self.removePath()

    def focus(self):
        self.focusEvent.emit()

    def _focus(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def addDevice(self, dev: OptomechDevice):
        self.newDeviceSignal.emit(dev)

    def _addDevice(self, dev: OptomechDevice):
        dev.sigGeometryChanged.connect(self.handleGeometryChange)
        self._geometries.setdefault(dev, {})
        if (geom := dev.getGeometry()) is None:
            return
        self._geometries[dev]["geom"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._geometries[dev]["mesh"] = mesh

        dev.sigGlobalTransformChanged.connect(self.handleTransformUpdate)
        self.handleTransformUpdate(dev, dev)

    def _removeDevice(self, dev):
        if dev not in self._geometries:
            return
        dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
        mesh = self._geometries[dev].get("mesh")
        if mesh is None:
            return
        dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)
        self.view.removeItem(mesh)

    def handleTransformUpdate(self, moved_device: OptomechDevice, cause_device: OptomechDevice):
        geom = self._geometries.get(moved_device, {}).get("geom")
        if geom is None:
            return
        xform = moved_device.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self._geometries[moved_device]["mesh"].setTransform(xform)

    def handleGeometryChange(self, dev: OptomechDevice):
        self._removeDevice(dev)
        self._geometries[dev] = {}
        self.addDevice(dev)

    def startPath(self, start, stop, voxel_size, bounds):
        self.pathStartSignal.emit(start, stop, voxel_size, bounds)

    def _startPath(self, start, stop, voxel_size, bounds):
        self.removePath()
        path = gl.GLLinePlotItem(pos=np.array([start, stop]), color=(0.1, 1, 0.7, 1), width=1)
        self.view.addItem(path)
        self._path["path"] = path
        start_target = gl.GLScatterPlotItem(
            pos=np.array([start]), color=(0, 0, 1, 1), size=voxel_size * 2, pxMode=False
        )
        self.view.addItem(start_target)
        self._path["start target"] = start_target

        dest_target = gl.GLScatterPlotItem(pos=np.array([stop]), color=(0, 1, 0, 1), size=voxel_size * 2, pxMode=False)
        self.view.addItem(dest_target)
        self._path["dest target"] = dest_target

        for a, b in Plane.wireframe(*bounds):
            edge = gl.GLLinePlotItem(pos=np.array([a, b]), color=(1, 0, 0, 0.2), width=1)
            self.view.addItem(edge)
            self._path[(tuple(a), tuple(b))] = edge

    def addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform):
        self.newObstacleSignal.emit(obstacle, to_global)

    def _addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform):
        verts, faces = obstacle.surface_mesh
        mesh = gl.MeshData(vertexes=verts, faces=faces)
        m = gl.GLMeshItem(
            meshdata=mesh, smooth=True, color=(0.1, 0.1, 0.3, 0.25), shader="balloon", glOptions="additive"
        )
        m.setTransform((to_global * obstacle.transform).as_pyqtgraph())
        self.view.addItem(m)
        self._path[obstacle] = m

    def updatePath(self, path, skip=4):
        self._pathUpdates.put((path, skip))

    def _watchForPathUpdates(self):
        n_updates = 0
        while True:
            path, skip = self._pathUpdates.get()
            n_updates += 1
            if n_updates % skip == 0:
                self.pathUpdateSignal.emit(path, skip)
                time.sleep(0.02)

    def _updatePath(self, path, skip):
        if "path" not in self._path:
            return
        self._path["path"].setData(pos=path)

    def removePath(self):
        for viz in self._path.values():
            self.view.removeItem(viz)
        self._path = {}
