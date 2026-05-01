from collections import OrderedDict
from typing import Union

import numpy as np
import scipy
import time

import acq4.util.functions as fn
import acq4.util.ptime as ptime
import pyqtgraph as pg
from acq4.devices.Camera import Camera, CameraTask
from acq4.devices.Camera.deviceGUI import CameraDeviceGui
from acq4.util import Qt
from acq4.util.Mutex import Mutex

WIDTH = 512
HEIGHT = 512

_ZSTACK_CONFIG_FILE = "zstack_images"


class MockCamera(Camera):
    sigZStackChanged = Qt.Signal(object)  # emits objective name (str)

    def __init__(self, manager, config, name):
        self.ringSize = 100
        self.frameId = 0
        self.noise = np.random.normal(size=10000000, loc=100, scale=10)  # pre-generate noise for use in images

        # Track which objectives have config-file-locked z-stacks (no UI editing allowed)
        self._configLockedImages = set(config.get("images", {}).keys())

        if "images" in config:
            self.bgData = {}
            self.bgInfo = {}
            for obj, filename in config["images"].items():
                self._loadZStack(obj, filename, manager=manager)
        else:
            self.bgData = mandelbrot(width=WIDTH * 5, maxIter=60).astype(np.float32)
            self.bgInfo = None

        self.background = None

        self.params = OrderedDict(
            [
                ("triggerMode", "Normal"),
                ("exposure", 0.001),
                # ("binning", (1, 1)),
                # ("region", (0, 0, WIDTH, WIDTH)),
                ("binningX", 1),
                ("binningY", 1),
                ("regionX", 0),
                ("regionY", 0),
                ("regionW", WIDTH),
                ("regionH", HEIGHT),
                ("gain", 1.0),
                ("sensorSize", (WIDTH, HEIGHT)),
                ("bitDepth", 16),
            ]
        )

        self.paramRanges = OrderedDict(
            [
                ("triggerMode", (["Normal", "TriggerStart"], True, True, [])),
                ("exposure", ((0.001, 10.0), True, True, [])),
                # ("binning", ([range(1, 10), range(1, 10)], True, True, [])),
                # ("region", ([(0, WIDTH - 1), (0, HEIGHT - 1), (1, WIDTH), (1, HEIGHT)], True, True, [])),
                ("binningX", (list(range(1, 10)), True, True, [])),
                ("binningY", (list(range(1, 10)), True, True, [])),
                ("regionX", ((0, WIDTH - 1), True, True, ["regionW"])),
                ("regionY", ((0, HEIGHT - 1), True, True, ["regionH"])),
                ("regionW", ((1, WIDTH), True, True, ["regionX"])),
                ("regionH", ((1, HEIGHT), True, True, ["regionY"])),
                ("gain", ((0.1, 10.0), True, True, [])),
                ("sensorSize", (None, False, True, [])),
                ("bitDepth", (None, False, True, [])),
            ]
        )

        self.groupParams = {
            "binning": ("binningX", "binningY"),
            "region": ("regionX", "regionY", "regionW", "regionH"),
        }

        sig = np.random.normal(size=(WIDTH, HEIGHT), loc=1.0, scale=0.3)
        sig = scipy.ndimage.gaussian_filter(sig, (3, 3))
        sig[20:40, 20:40] += 1
        sig[sig < 0] = 0
        self.signal = sig

        Camera.__init__(self, manager, config, name)  # superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastIndex = None
        self.lastFrameTime = None
        self.stopOk = False

        self.sigGlobalTransformChanged.connect(self.globalTransformChanged)

        # generate list of mock cells
        cells = np.zeros(
            20,
            dtype=[
                ("x", float),
                ("y", float),
                ("size", float),
                ("value", float),
                ("rate", float),
                ("intensity", float),
                ("decayTau", float),
            ],
        )
        cells["x"] = np.random.normal(size=cells.shape, scale=100e-6, loc=-1.5e-3)
        cells["y"] = np.random.normal(size=cells.shape, scale=100e-6, loc=4.4e-3)
        cells["size"] = np.random.normal(size=cells.shape, scale=2e-6, loc=10e-6)
        cells["rate"] = np.random.lognormal(size=cells.shape, mean=0, sigma=1) * 1.0
        cells["intensity"] = np.random.uniform(size=cells.shape, low=1000, high=10000)
        cells["decayTau"] = np.random.uniform(size=cells.shape, low=15e-3, high=500e-3)
        self.cells = cells

        # Load user-set z-stacks saved from a previous session, for objectives not already
        # locked by the device config.
        self._loadSavedZStacks()

    def _loadZStack(self, obj_name, filepath, manager=None):
        """Load a z-stack MetaArray file for the given objective.

        Stores the pixel data and z-depth axis into bgData/bgInfo, sorted ascending by depth.
        Uses the acq4 DataManager/FileHandle machinery when available.
        """
        if manager is None:
            manager = self.dm
        try:
            fh = manager.fileHandle(filepath)
            ma = fh.read()
        except Exception:
            # Fall back to direct load if the path is outside the manager root
            from acq4.util.DataManager import getHandle
            fh = getHandle(filepath)
            ma = fh.read()

        data = ma.asarray()

        # Two on-disk formats: 'Depth' axis stores z directly in xvals(0); 'Time' axis
        # (recorded as a time-series z-stack) stores per-frame global positions separately.
        axis0_info = ma.infoCopy()[0]
        if axis0_info.get("name") == "Depth":
            depths = ma.xvals(0)
        elif "globalPosition" in axis0_info:
            depths = axis0_info["globalPosition"][:, 2]
        else:
            raise ValueError(f"Cannot determine z-positions from MetaArray in '{filepath}'")

        # Sort z-axis ascending so searchsorted works correctly
        order = np.argsort(depths)
        depths = depths[order]
        data = data[order]

        if not isinstance(self.bgData, dict):
            # First time converting from Mandelbrot to dict mode
            self.bgData = {}
            self.bgInfo = {}

        self.bgData[obj_name] = data
        self.bgInfo[obj_name] = {
            "depths": depths,
            "filename": str(filepath),
            "config_locked": obj_name in self._configLockedImages,
        }
        self.background = None

    def clearZStack(self, obj_name):
        """Remove the user-set z-stack for the given objective and save the change."""
        if obj_name in self._configLockedImages:
            raise ValueError(f"Cannot clear config-locked z-stack for objective '{obj_name}'")
        if isinstance(self.bgData, dict):
            self.bgData.pop(obj_name, None)
            self.bgInfo.pop(obj_name, None)
        self.background = None
        self._saveZStacks()
        self.sigZStackChanged.emit(obj_name)

    def loadZStack(self, obj_name, filepath):
        """Load a z-stack from filepath for the given objective, then persist and signal."""
        self._loadZStack(obj_name, filepath)
        self._saveZStacks()
        self.sigZStackChanged.emit(obj_name)

    def _saveZStacks(self):
        """Write user-set z-stack filenames to the device config file."""
        if not isinstance(self.bgInfo, dict):
            return
        user_stacks = {
            obj: info["filename"]
            for obj, info in self.bgInfo.items()
            if not info.get("config_locked", False)
        }
        self.writeConfigFile(user_stacks, _ZSTACK_CONFIG_FILE)

    def _loadSavedZStacks(self):
        """Load user-set z-stacks from the device config file, skipping config-locked objectives."""
        try:
            saved = self.readConfigFile(_ZSTACK_CONFIG_FILE)
        except Exception:
            return
        if not isinstance(saved, dict):
            return
        for obj_name, filepath in saved.items():
            if obj_name in self._configLockedImages:
                continue
            try:
                self._loadZStack(obj_name, filepath)
            except Exception as exc:
                print(f"MockCamera: could not load saved z-stack for '{obj_name}' ({filepath}): {exc}")

    def listObjectivesForUI(self):
        """Return an ordered list of objective names for UI display.

        Includes config-locked objectives first, then any UI-set or scope-available objectives.
        """
        names = list(self._configLockedImages)

        if isinstance(self.bgInfo, dict):
            for k in self.bgInfo:
                if k not in names:
                    names.append(k)

        if self.scopeDev is not None:
            for obj in self.scopeDev.listObjectives():
                n = obj.name()
                if n not in names:
                    names.append(n)

        return names

    def setupCamera(self):
        pass

    def globalTransformChanged(self):
        self.background = None

    def startCamera(self):
        self.lastFrameTime = ptime.time()

    def stopCamera(self):
        self.lastFrameTime = None

    def getNoise(self, shape):
        n = shape[0] * shape[1]
        s = np.random.randint(len(self.noise) - n)
        d = self.noise[s : s + n]
        d.shape = shape
        return np.abs(d)

    def getBackground(self):
        if self.background is None:
            w, h = self.params["sensorSize"]
            tr = self.globalTransform().as_pyqtgraph()

            if isinstance(self.bgData, dict):
                obj = self.getObjective()
                if obj is not None and obj in self.bgData:
                    self.background = self._getZStackBackground(obj, w, h, tr)
                else:
                    # No z-stack for this objective: black
                    self.background = np.zeros((w, h), dtype=np.uint16)
            else:
                tr = pg.SRTTransform(tr)
                m = Qt.QTransform()

                m.scale(3e6, 3e6)
                m.translate(0.0005, 0.0005)
                tr = tr * m

                origin = tr.map(pg.Point(0, 0))
                x = tr.map(pg.Point(1, 0)) - origin
                y = tr.map(pg.Point(0, 1)) - origin
                origin = np.array([origin.x(), origin.y()])
                x = np.array([x.x(), x.y()])
                y = np.array([y.x(), y.y()])

                # slice fractal from pre-rendered data
                vectors = (x, y)
                self.background = pg.affineSlice(self.bgData, (w, h), origin, vectors, (0, 1), order=1)

        return self.background

    def _getZStackBackground(self, obj, w, h, tr):
        """Return a (w, h) background image for the given objective using z-only matching.

        Returns a black image when z falls outside the stack's depth range.
        """
        data = self.bgData[obj]     # shape (nz, bw, bh), depths sorted ascending
        depths = self.bgInfo[obj]["depths"]

        # Extract world-space z from the global transform
        origin = tr.map(pg.Vector(0, 0, 0))
        z = origin.z()

        z_min = depths[0]
        z_max = depths[-1]
        if z < z_min or z > z_max:
            return np.zeros((w, h), dtype=data.dtype)

        # Interpolate between the two nearest z slices
        z1_idx = int(np.clip(np.searchsorted(depths, z, side="right") - 1, 0, len(depths) - 2))
        z2_idx = z1_idx + 1
        dz = depths[z2_idx] - depths[z1_idx]
        s = 0.0 if dz == 0 else float(np.clip((z - depths[z1_idx]) / dz, 0.0, 1.0))

        slice_img = data[z1_idx].astype(np.float32) * (1.0 - s) + data[z2_idx].astype(np.float32) * s

        # Center-crop (or center-pad) the z-slice to the sensor size
        bw, bh = data.shape[1], data.shape[2]
        src_x = max(0, (bw - w) // 2)
        src_y = max(0, (bh - h) // 2)
        dst_x = max(0, (w - bw) // 2)
        dst_y = max(0, (h - bh) // 2)
        copy_w = min(w, bw)
        copy_h = min(h, bh)

        bg = np.zeros((w, h), dtype=data.dtype)
        bg[dst_x : dst_x + copy_w, dst_y : dst_y + copy_h] = slice_img[
            src_x : src_x + copy_w, src_y : src_y + copy_h
        ].astype(data.dtype)
        return bg

    def pixelVectors(self):
        tr = self.globalTransform()
        origin = tr.map(np.asarray((0, 0, 0)))
        x = tr.map(np.asarray((1, 0, 0))) - origin
        y = tr.map(np.asarray((0, 1, 0))) - origin

        return x[:2], y[:2]

    def _acquireFrames(self, n: int):
        self.startCamera()
        try:
            frames = []
            while True:
                frames.extend([f["data"][np.newaxis, ...] for f in self.newFrames()])
                if len(frames) >= n or not self._cameraRunning():
                    break
                time.sleep(0.1)
        finally:
            self.stopCamera()

        return np.concatenate(frames[:n])

    def _cameraRunning(self):
        return self.lastFrameTime is not None

    def newFrames(self):
        """Return a list of all frames acquired since the last call to newFrames."""
        prof = pg.debug.Profiler(disabled=True)

        if self.lastFrameTime is None:
            return []

        now = ptime.time()
        dt = now - self.lastFrameTime
        exp = self.getParam("exposure")
        bin = self.getParam("binning")
        fps = 1.0 / (exp + (40e-3 / (bin[0] * bin[1])))
        nf = int(dt * fps)
        if nf == 0:
            return []
        self.lastFrameTime = now + exp

        prof()
        region = self.getParam("region")
        prof()
        bg = self.getBackground()[region[0] : region[0] + region[2], region[1] : region[1] + region[3]]
        prof()

        # Start with noise
        shape = region[2:]
        data = self.getNoise(shape)
        # data = np.zeros(shape, dtype=float)
        prof()

        # Add specimen
        data += bg * (exp * 10)
        prof()

        # update cells
        spikes = np.random.poisson(min(dt, 0.4) * self.cells["rate"])
        self.cells["value"] *= np.exp(-dt / self.cells["decayTau"])
        self.cells["value"] = np.clip(self.cells["value"] + spikes * 0.2, 0, 1)
        data[data < 0] = 0

        # draw cells
        px = (self.pixelVectors()[0] ** 2).sum() ** 0.5

        # Generate transform that maps grom global coordinates to image coordinates
        cameraTr = self.inverseGlobalTransform()
        # note we use binning=(1,1) here because the image is downsampled later.
        frameTr = self.makeFrameTransform(region, [1, 1]).inverse
        tr = frameTr * cameraTr

        for cell in self.cells:
            w = cell["size"] / px
            pos = (cell["x"], cell["y"], 0)
            imgPos = tr.map(pos)
            start = (int(imgPos[0]), int(imgPos[1]))
            stop = (int(start[0] + w), int(start[1] + w))
            val = cell["intensity"] * cell["value"] * self.getParam("exposure")
            data[max(0, start[0]) : max(0, stop[0]), max(0, start[1]) : max(0, stop[1])] += val

        # Binning
        if bin[0] > 1:
            data = fn.downsample(data, bin[0], axis=0)
        if bin[1] > 1:
            data = fn.downsample(data, bin[1], axis=1)
        data = data.astype(np.uint16)
        prof()

        self.frameId += 1
        frames = [{"data": data, "time": now + (i / fps), "id": self.frameId} for i in range(nf)]
        prof()
        return frames

    def quit(self):
        pass

    def listParams(self, params: Union[list, str, None] = None):
        """List properties of specified parameter(s), or of all parameters if None"""
        if params is None:
            return self.paramRanges
        if isinstance(params, str):
            return self.paramRanges[params]

        return {k: self.paramRanges[k] for k in params}

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        if isinstance(params, list):
            params = dict(params)
        dp = []
        ap = {}
        for k in params:
            if k in self.groupParams:
                ap.update(dict(zip(self.groupParams[k], params[k])))
                dp.append(k)
        params.update(ap)
        for k in dp:
            del params[k]

        self.params.update(params)
        newVals = params
        restart = True
        if autoRestart and restart:
            self.restart()
        self.sigParamsChanged.emit(newVals)
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = list(self.listParams().keys())
        vals = OrderedDict()
        for k in params:
            if k in self.groupParams:
                vals[k] = list(self.getParams(self.groupParams[k]).values())
            else:
                vals[k] = self.params[k]
        return vals

    def createTask(self, cmd, parentTask):
        with self.lock:
            return MockCameraTask(self, cmd, parentTask)

    def deviceInterface(self, win):
        return MockCameraDeviceGui(self, win)


class MockCameraDeviceGui(CameraDeviceGui):
    """Camera device GUI for MockCamera, extending the standard camera controls with
    per-objective z-stack file selection, z-range display, and clear controls.
    """

    def __init__(self, dev, win):
        CameraDeviceGui.__init__(self, dev, win)

        self._objWidgets = {}  # obj_name -> dict of widgets

        zstackSection = Qt.QWidget()
        sectionLayout = Qt.QVBoxLayout()
        sectionLayout.setContentsMargins(4, 4, 4, 4)
        zstackSection.setLayout(sectionLayout)

        headerLabel = Qt.QLabel("<b>Z-Stack Images</b>")
        sectionLayout.addWidget(headerLabel)

        objectives = dev.listObjectivesForUI()
        if not objectives:
            sectionLayout.addWidget(Qt.QLabel("(no objectives configured)"))
        else:
            for obj_name in objectives:
                group = self._buildObjectiveGroup(obj_name)
                sectionLayout.addWidget(group)

        self.layout.addWidget(zstackSection)
        dev.sigZStackChanged.connect(self._onZStackChanged)

    def _buildObjectiveGroup(self, obj_name):
        """Build and return a QGroupBox for one objective's z-stack controls."""
        config_locked = obj_name in self.dev._configLockedImages

        group = Qt.QGroupBox(obj_name)
        layout = Qt.QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        group.setLayout(layout)

        # Z-range label
        rangeLabel = Qt.QLabel()
        layout.addWidget(rangeLabel)

        widgets = {"rangeLabel": rangeLabel}

        if not config_locked:
            btnRow = Qt.QWidget()
            btnLayout = Qt.QHBoxLayout()
            btnLayout.setContentsMargins(0, 0, 0, 0)
            btnRow.setLayout(btnLayout)

            loadBtn = Qt.QPushButton("Load z-stack...")
            clearBtn = Qt.QPushButton("Clear")
            btnLayout.addWidget(loadBtn)
            btnLayout.addWidget(clearBtn)
            btnLayout.addStretch()
            layout.addWidget(btnRow)

            loadBtn.clicked.connect(lambda checked, n=obj_name: self._onLoadClicked(n))
            clearBtn.clicked.connect(lambda checked, n=obj_name: self._onClearClicked(n))

            widgets["loadBtn"] = loadBtn
            widgets["clearBtn"] = clearBtn

        self._objWidgets[obj_name] = widgets
        self._updateObjectiveUI(obj_name)
        return group

    def _updateObjectiveUI(self, obj_name):
        """Refresh the z-range label and button visibility for one objective."""
        widgets = self._objWidgets.get(obj_name)
        if widgets is None:
            return

        bgInfo = self.dev.bgInfo
        if isinstance(bgInfo, dict) and obj_name in bgInfo:
            depths = bgInfo[obj_name]["depths"]
            z_min_um = depths[0] * 1e6
            z_max_um = depths[-1] * 1e6
            fname = bgInfo[obj_name].get("filename", "")
            import os
            short_name = os.path.basename(fname)
            widgets["rangeLabel"].setText(
                f"<small>{short_name}</small><br>Z range: {z_min_um:.1f} – {z_max_um:.1f} µm"
            )
            if "clearBtn" in widgets:
                widgets["clearBtn"].setEnabled(True)
        else:
            widgets["rangeLabel"].setText("No z-stack loaded")
            if "clearBtn" in widgets:
                widgets["clearBtn"].setEnabled(False)

    def _onLoadClicked(self, obj_name):
        path, _ = Qt.QFileDialog.getOpenFileName(
            self,
            f"Select z-stack for {obj_name}",
            "",
            "MetaArray files (*.ma)",
        )
        if not path:
            return
        try:
            self.dev.loadZStack(obj_name, path)
        except Exception as exc:
            Qt.QMessageBox.warning(self, "Load failed", str(exc))

    def _onClearClicked(self, obj_name):
        self.dev.clearZStack(obj_name)

    def _onZStackChanged(self, obj_name):
        self._updateObjectiveUI(obj_name)


class MockCameraTask(CameraTask):
    """Generate exposure waveform when recording with mockcamera.
    """

    def __init__(self, dev, cmd, parentTask):
        CameraTask.__init__(self, dev, cmd, parentTask)
        self._DAQCmd["exposure"]["lowLevelConf"] = {"mockFunc": self.makeExpWave}
        self.frameTimes = []

    def makeExpWave(self):
        # Called by DAQGeneric to simulate a read-from-DAQ
        # first look up the DAQ configuration so we know the sample rate / number
        daq = self.dev.listChannels()["exposure"]["device"]
        cmd = self.parentTask().tasks[daq].cmd
        start = self.parentTask().startTime
        sampleRate = cmd["rate"]
        numPts = cmd["numPts"]
        data = np.zeros(numPts, dtype=np.uint8)
        if self.fixedFrameCount is None:
            frames = self._future.peekAtResult()  # not exact, but close enough for a mock
            for f in frames:
                t = f.info()["time"]
                exp = f.info()["exposure"]
                i0 = int((t - start) * sampleRate)
                i1 = i0 + int((exp - 0.1e-3) * sampleRate)
                data[i0:i1] = 1
        else:
            n = self.fixedFrameCount
            exp = int((self.dev.getParam("exposure") - 0.1e-3) * sampleRate)
            minLength = max(numPts - exp, exp * n)
            for i0 in np.linspace(1, minLength - 2, n, dtype=int):
                i1 = i0 + exp
                data[i0:i1] = 1

        return data


def mandelbrot(width=500, height=None, maxIter=20, xRange=(-2.0, 1.0), yRange=(-1.2, 1.2)):
    x0, x1 = xRange
    y0, y1 = yRange
    if height is None:
        height = int(width * (y1 - y0) / (x1 - x0))

    x = np.linspace(x0, x1, width).reshape(width, 1)
    y = np.linspace(y0, y1, height).reshape(1, height)

    # speed up with a clever initial mask:
    x14 = x - 0.25
    y2 = y ** 2
    q = x14 ** 2 + y2
    mask = q * (q + x14) > 0.25 * y2
    mask &= (x + 1) ** 2 + y2 > 1 / 16.0
    mask &= x > -2
    mask &= x < 0.7
    mask &= y > -1.2
    mask &= y < 1.2

    img = np.zeros((width, height), dtype=int)
    xInd, yInd = np.mgrid[0:width, 0:height]
    x = x.reshape(width)[xInd]
    y = y.reshape(height)[yInd]
    z0 = np.empty((width, height), dtype=np.complex64)
    z0.real = x
    z0.imag = y
    z = z0.copy()

    for i in range(maxIter):
        z = z[mask]
        z0 = z0[mask]
        xInd = xInd[mask]
        yInd = yInd[mask]
        z *= z
        z += z0
        mask = np.abs(z) < 2.0
        img[xInd[mask], yInd[mask]] = i % (maxIter - 1)

    return img
