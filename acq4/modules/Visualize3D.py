import os
import queue
import time
from threading import Thread
from typing import Union

import numpy as np

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.Qt import FlowLayout
from acq4.util.geometry import Plane, Volume, Geometry
from acq4.util.threadrun import runInGuiThread
from coorx import Transform, TTransform
from pyqtgraph import opengl as gl
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem


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


class VisualizerWindow(Qt.QMainWindow):
    pathStartSignal = Qt.pyqtSignal(object, object, list)
    newObstacleSignal = Qt.pyqtSignal(object, object)
    newDeviceSignal = Qt.pyqtSignal(object)
    pathUpdateSignal = Qt.pyqtSignal(object, int)
    focusEvent = Qt.pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("3D Visualization of all Optomech Devices")
        self.setGeometry(50, 50, 800, 600)
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), "icons.svg")))
        self.layout = Qt.QGridLayout()
        self.setCentralWidget(Qt.QWidget())
        self.centralWidget().setLayout(self.layout)

        self.view = gl.GLViewWidget()
        self.layout.addWidget(self.view, 0, 0, 8, 1)
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

        button_zone = Qt.QWidget()
        self.button_layout = FlowLayout()
        button_zone.setLayout(self.button_layout)
        self.layout.addWidget(button_zone, 9, 0)

        self.pathPlanToggler = Qt.QCheckBox("Show Path Plan")
        self.pathPlanToggler.setEnabled(False)
        self.pathPlanToggler.stateChanged.connect(self.togglePathPlan)
        self.button_layout.addWidget(self.pathPlanToggler)

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

    def _addDevice(self, dev: Union[Device, OptomechDevice]):
        dev.sigGeometryChanged.connect(self.handleGeometryChange)
        if (geom := dev.getGeometry()) is None:
            return
        self.addGeometry(geom, dev)
        dev.sigGlobalTransformChanged.connect(self.handleTransformUpdate)
        self.handleTransformUpdate(dev, dev)
        display_checkbox = Qt.QCheckBox(dev.name())
        display_checkbox.setChecked(True)
        display_checkbox.setObjectName(dev.name())
        display_checkbox.stateChanged.connect(self.toggleDeviceVisibility)
        self.button_layout.addWidget(display_checkbox)
        self._geometries[dev]["display_checkbox"] = display_checkbox
        if bounds := dev.getBoundaries():
            self._geometries[dev]["limits"] = {}
            self.addBounds(bounds, self._geometries[dev]["limits"])
            wireframe_checkbox = Qt.QCheckBox(f"{dev.name()} limits")
            wireframe_checkbox.setChecked(False)
            wireframe_checkbox.setObjectName(dev.name())
            wireframe_checkbox.stateChanged.connect(self.toggleDeviceLimitsVisibility)
            self.button_layout.addWidget(wireframe_checkbox)
            self._geometries[dev]["wireframe_checkbox"] = wireframe_checkbox
            self.toggleDeviceLimitsVisibility(Qt.QtCore.Qt.Unchecked, dev.name())
            if hasattr(dev, "sigCalibrationChanged"):
                dev.sigCalibrationChanged.connect(self.handleGeometryChange)

    def toggleDeviceVisibility(self, state):
        dev_name = self.sender().objectName()
        for key, data in self._geometries.items():
            if key.name() == dev_name:
                data["mesh"].setVisible(state == Qt.QtCore.Qt.Checked)

    def addBounds(self, bounds, displayables_container: dict):
        for a, b in Plane.wireframe(*bounds):
            if np.linalg.norm(a - b) > 0.1:
                continue  # ignore bounds that are really far away
            edge = gl.GLLinePlotItem(pos=np.array([a, b]), color=(1, 0, 0, 0.2), width=1)
            self.view.addItem(edge)
            displayables_container[(tuple(a), tuple(b))] = edge

    def toggleDeviceLimitsVisibility(self, state, dev_name=None):
        dev_name = dev_name or self.sender().objectName()
        for key, data in self._geometries.items():
            if key.name() == dev_name:
                for edge in data.get("limits", {}).values():
                    edge.setVisible(state == Qt.QtCore.Qt.Checked)

    def addGeometry(self, geom: Geometry, key=None):
        if key is None:
            key = geom.name
        self._geometries.setdefault(key, {})
        self._geometries[key]["geom"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._geometries[key]["mesh"] = mesh

    def _removeDevice(self, dev):
        if dev not in self._geometries:
            return
        dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
        mesh = self._geometries[dev].get("mesh")
        if mesh is None:
            return
        dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)
        self.view.removeItem(mesh)
        for edge in self._geometries[dev].get("limits", {}).values():
            self.view.removeItem(edge)
            edge.deleteLater()
        disp_check = self._geometries[dev]["display_checkbox"]
        self.button_layout.removeWidget(disp_check)
        disp_check.deleteLater()
        if "wireframe_checkbox" in self._geometries[dev]:
            wf_check = self._geometries[dev]["wireframe_checkbox"]
            self.button_layout.removeWidget(wf_check)
            wf_check.deleteLater()

    def handleTransformUpdate(self, moved_device: OptomechDevice, cause_device: OptomechDevice):
        geom = self._geometries.get(moved_device, {}).get("geom")
        if geom is None:
            return
        xform = moved_device.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self.setMeshTransform(moved_device, xform)

    def setMeshTransform(self, dev, xform):
        self._geometries[dev]["mesh"].setTransform(xform)

    def handleGeometryChange(self, dev: OptomechDevice):
        self._removeDevice(dev)
        self._geometries[dev] = {}
        self.addDevice(dev)

    def startPath(self, start, stop, bounds):
        self.pathStartSignal.emit(start, stop, bounds)

    def _startPath(self, start, stop, bounds):
        self.removePath()
        self.pathPlanToggler.setEnabled(True)
        self.pathPlanToggler.setChecked(True)
        path = gl.GLLinePlotItem(pos=np.array([start, stop]), color=(0.1, 1, 0.7, 1), width=1)
        self.view.addItem(path)
        self._path["path"] = path
        start_target = gl.GLScatterPlotItem(pos=np.array([start]), color=(0, 0, 1, 1), size=10, pxMode=True)
        self.view.addItem(start_target)
        self._path["start target"] = start_target

        dest_target = gl.GLScatterPlotItem(pos=np.array([stop]), color=(0, 1, 0, 1), size=10, pxMode=True)
        self.view.addItem(dest_target)
        self._path["dest target"] = dest_target

        self.addBounds(bounds, self._path)

    def addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform):
        self.newObstacleSignal.emit(obstacle, to_global)

    def _addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform):
        verts, faces = obstacle.surface_mesh
        mesh = gl.MeshData(vertexes=verts, faces=faces)
        m = gl.GLMeshItem(
            meshdata=mesh, smooth=True, color=(0.1, 0.1, 0.3, 0.25), shader="balloon", glOptions="additive"
        )
        cs_name = obstacle.transform.systems[0].name
        recenter_voxels = TTransform(
            offset=(0.5, 0.5, 0.5),
            from_cs=f"[isosurface of {cs_name}]",
            to_cs=cs_name,
        )
        m.setTransform((to_global * obstacle.transform * recenter_voxels).as_pyqtgraph())
        self.view.addItem(m)
        self._path[obstacle] = m

        # vol = np.zeros(obstacle.volume.T.shape + (4,), dtype=np.ubyte)
        # vol[..., :3] = (30, 10, 10)
        # vol[..., 3] = obstacle.volume.T * 5
        # v = gl.GLVolumeItem(vol, sliceDensity=10, smooth=False, glOptions="additive")
        # v.setTransform((to_global * obstacle.transform).as_pyqtgraph())
        # self.view.addItem(v)
        # self._path[f"voxels of {cs_name}"] = v

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

    def togglePathPlan(self, state):
        visible = state == Qt.QtCore.Qt.Checked
        for viz in self._path.values():
            viz.setVisible(visible)

    def removePath(self):
        for viz in self._path.values():
            self.view.removeItem(viz)
        self._path = {}
        self.pathPlanToggler.setChecked(False)
