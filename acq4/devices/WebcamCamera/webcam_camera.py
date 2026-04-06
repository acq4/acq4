from __future__ import annotations

from collections import OrderedDict
import queue
import threading
import time

import numpy as np

import acq4.util.ptime as ptime
from acq4.devices.Camera import Camera

try:
    import cv2
except ImportError:
    cv2 = None


class WebcamCamera(Camera):
    """
    Minimal camera driver using OpenCV VideoCapture.

    This implementation intentionally keeps behavior simple:
    - Uses a configured capture resolution as the effective sensor size.
    - Streams frames continuously via ``newFrames``.
    - Keeps trigger mode, ROI, and binning fixed to basic values.
    - Exposes a small set of optional cv2 controls when available.

    Configuration options (exactly one of ``cameraIndex`` or ``cameraName`` must be provided):

    - ``cameraIndex`` (int): Webcam index for cv2.VideoCapture.
    - ``cameraName`` (str): Substring of the camera's device description (case-insensitive).
      If omitted along with ``cameraIndex``, an exception is raised that lists all
      available ``index: description`` pairs so you can copy one into the config.
    - ``backend`` (int | str, optional): OpenCV backend (for example "CAP_DSHOW").
    - ``resolution`` ([w, h], default [640, 480]): Requested capture size used as effective sensor size.
    - ``colorMode`` ("gray" | "bgr", default "gray"): Output frame format.
    - ``bufferSize`` (int, optional): Requested driver buffer size.
    - ``pixelFormat`` (str, optional): Initial FOURCC string (for example "MJPG").
    - ``pixelFormats`` ([str], optional): Allowed pixel format values exposed in UI.
    """

    _OPTIONAL_CV2_PARAMS = (
        ("brightness", "CAP_PROP_BRIGHTNESS", (0.0, 1.0), False),
        ("contrast", "CAP_PROP_CONTRAST", (0.0, 1.0), False),
        ("saturation", "CAP_PROP_SATURATION", (0.0, 1.0), False),
        ("hue", "CAP_PROP_HUE", (0.0, 1.0), False),
        ("gain", "CAP_PROP_GAIN", (0.0, 255.0), False),
        ("gamma", "CAP_PROP_GAMMA", (0.0, 500.0), False),
        ("sharpness", "CAP_PROP_SHARPNESS", (0.0, 255.0), False),
        ("focus", "CAP_PROP_FOCUS", (0.0, 255.0), False),
        ("autoFocus", "CAP_PROP_AUTOFOCUS", None, True),
        ("autoExposure", "CAP_PROP_AUTO_EXPOSURE", (0.0, 1.0), False),
        ("whiteBalance", "CAP_PROP_WHITE_BALANCE_BLUE_U", (0.0, 10000.0), False),
        ("temperature", "CAP_PROP_TEMPERATURE", (2000.0, 10000.0), False),
        ("zoom", "CAP_PROP_ZOOM", (1.0, 10.0), False),
        ("frameRate", "CAP_PROP_FPS", (1.0, 240.0), False),
        ("cvExposure", "CAP_PROP_EXPOSURE", (-20.0, 20.0), False),
    )

    @staticmethod
    def _enumerate_devices() -> list[tuple[int, str]]:
        """Return a list of (index, description) for available camera devices.

        Tries pygrabber (Windows DirectShow) for human-readable names first,
        then falls back to probing indices 0–9 with cv2.VideoCapture.
        """
        if cv2 is None:
            return []

        # Windows DirectShow: pygrabber gives real device names.
        try:
            from pygrabber.dshow_graph import FilterGraph  # type: ignore

            graph = FilterGraph()
            return list(enumerate(graph.get_input_devices()))
        except Exception:
            pass

        # Generic fallback: probe indices and report which ones open.
        devices = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                devices.append((i, f"Camera {i}"))
                cap.release()
        return devices

    @staticmethod
    def _findCameraByName(name: str) -> int:
        """Return the index of the first camera whose description contains *name* (case-insensitive).

        Raises ``ValueError`` with the device list if no match is found.
        """
        devices = WebcamCamera._enumerate_devices()
        name_lower = name.lower()
        for idx, desc in devices:
            if name_lower in desc.lower():
                return idx
        lines = "\n".join(f"  {idx}: {desc}" for idx, desc in devices)
        raise ValueError(
            f"No camera found matching name {name!r}.\nAvailable devices:\n{lines}"
        )

    def __init__(self, dm, config, name):
        self._capture = None

        if "cameraIndex" in config or "index" in config:
            self._cameraIndex = int(config.get("cameraIndex", config.get("index")))
        elif "cameraName" in config:
            self._cameraIndex = self._findCameraByName(config["cameraName"])
        else:
            devices = self._enumerate_devices()
            lines = "\n".join(f"  {idx}: {desc}" for idx, desc in devices)
            raise ValueError(
                "WebcamCamera config must specify 'cameraIndex' (int) or 'cameraName' (str).\n"
                f"Available devices:\n{lines}"
            )
        self._requestedResolution = self._parseResolution(config.get("resolution", (640, 480)))
        self._colorMode = str(config.get("colorMode", "gray")).lower()
        if self._colorMode not in ("gray", "bgr"):
            raise ValueError("colorMode must be 'gray' or 'bgr'")

        self._frameId = 0
        self._cv2Props = {}
        self._boolCv2Params = set()
        self._pixelFormatChoices = []
        self._sensorSize = self._requestedResolution

        w, h = self._requestedResolution
        self.params = OrderedDict(
            [
                ("triggerMode", "Normal"),
                ("exposure", 0.03),
                ("binningX", 1),
                ("binningY", 1),
                ("regionX", 0),
                ("regionY", 0),
                ("regionW", w),
                ("regionH", h),
                ("sensorSize", (w, h)),
                ("bitDepth", 8),
            ]
        )
        self.paramRanges = OrderedDict(
            [
                ("triggerMode", (["Normal"], True, True, [])),
                ("exposure", ((0.0, 10.0), True, True, [])),
                ("binningX", ([1], True, True, [])),
                ("binningY", ([1], True, True, [])),
                ("regionX", ((0, max(0, w - 1)), True, True, ["regionW"])),
                ("regionY", ((0, max(0, h - 1)), True, True, ["regionH"])),
                ("regionW", ((1, w), True, True, ["regionX"])),
                ("regionH", ((1, h), True, True, ["regionY"])),
                ("sensorSize", (None, False, True, [])),
                ("bitDepth", (None, False, True, [])),
            ]
        )

        super().__init__(dm, config, name)

        self.frameQueue = queue.Queue(maxsize=100)
        self._cvAcqThread = threading.Thread(target=self._acquisitionLoop, daemon=True)
        self._cvAcqThread.start()

    @staticmethod
    def _parseResolution(value) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("resolution must be a 2-item list/tuple: [width, height]")
        w = int(value[0])
        h = int(value[1])
        if w <= 0 or h <= 0:
            raise ValueError("resolution values must be > 0")
        return w, h

    def _parseBackend(self):
        backend = self.config.get("backend", None)
        if backend is None:
            return None
        if isinstance(backend, int):
            return backend
        if isinstance(backend, str):
            if cv2 is None or not hasattr(cv2, backend):
                raise ValueError(f"Unknown OpenCV backend constant: {backend!r}")
            return getattr(cv2, backend)
        raise TypeError("backend must be int or str")

    def setupCamera(self):
        if cv2 is None:
            raise ImportError("WebcamCamera requires opencv-python (import cv2 failed)")

        self._openCapture()
        self._registerOptionalCv2Params()
        self._registerPixelFormatParam()

    def _openCapture(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None

        backend = self._parseBackend()
        if backend is None:
            cap = cv2.VideoCapture(self._cameraIndex)
        else:
            cap = cv2.VideoCapture(self._cameraIndex, backend)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open webcam at index {self._cameraIndex}")

        w_req, h_req = self._requestedResolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(w_req))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(h_req))

        if "bufferSize" in self.config and hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, float(int(self.config["bufferSize"])))

        self._capture = cap

        if "pixelFormat" in self.config and hasattr(cv2, "CAP_PROP_FOURCC"):
            try:
                code = self._encodeFourcc(self.config["pixelFormat"])
            except Exception:
                pass
            else:
                cap.set(cv2.CAP_PROP_FOURCC, float(code))

        w = int(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        h = int(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        if w <= 0 or h <= 0:
            w, h = w_req, h_req
        self._setSensorGeometry(w, h)

    def _setSensorGeometry(self, width: int, height: int):
        self._sensorSize = (width, height)
        self.params["sensorSize"] = (width, height)
        self.params["regionX"] = 0
        self.params["regionY"] = 0
        self.params["regionW"] = width
        self.params["regionH"] = height

        self.paramRanges["regionX"] = ((0, max(0, width - 1)), True, True, ["regionW"])
        self.paramRanges["regionY"] = ((0, max(0, height - 1)), True, True, ["regionH"])
        self.paramRanges["regionW"] = ((1, width), True, True, ["regionX"])
        self.paramRanges["regionH"] = ((1, height), True, True, ["regionY"])

    def _registerOptionalCv2Params(self):
        for name, cv_name, value_range, is_bool in self._OPTIONAL_CV2_PARAMS:
            if not hasattr(cv2, cv_name):
                continue
            prop_id = getattr(cv2, cv_name)
            val = self._capture.get(prop_id)
            if not np.isfinite(val):
                continue

            writable = bool(self._capture.set(prop_id, val))
            if not writable and abs(float(val)) < 1e-12:
                continue

            self._cv2Props[name] = prop_id
            if is_bool:
                self._boolCv2Params.add(name)
                self.params[name] = bool(round(val))
                self.paramRanges[name] = ([False, True], writable, True, [])
            else:
                self.params[name] = float(val)
                self.paramRanges[name] = (value_range, writable, True, [])

    def _registerPixelFormatParam(self):
        if not hasattr(cv2, "CAP_PROP_FOURCC"):
            return
        prop_id = cv2.CAP_PROP_FOURCC
        val = self._capture.get(prop_id)
        if not np.isfinite(val):
            return
        code = int(round(val))
        writable = bool(self._capture.set(prop_id, float(code)))
        if not writable and code == 0:
            return

        self._cv2Props["pixelFormat"] = prop_id
        current = self._decodeFourcc(code)
        configured = [str(v).upper() for v in self.config.get("pixelFormats", [])]
        choices = [current] + [v for v in configured if v not in (current, "")]
        self._pixelFormatChoices = choices
        self.params["pixelFormat"] = current
        self.paramRanges["pixelFormat"] = (choices, writable, True, [])

    @staticmethod
    def _decodeFourcc(code: int) -> str:
        chars = [chr((code >> (8 * i)) & 0xFF) for i in range(4)]
        text = "".join(ch for ch in chars if 32 <= ord(ch) <= 126)
        return text if len(text) == 4 else "UNKNOWN"

    @staticmethod
    def _encodeFourcc(text: str) -> int:
        text = str(text).upper()
        if len(text) != 4:
            raise ValueError("pixelFormat must be a 4-character FOURCC string")
        return cv2.VideoWriter_fourcc(*text)

    def _setFourcc(self, value, autoCorrect=True) -> str:
        if "pixelFormat" not in self._cv2Props:
            if not autoCorrect:
                raise ValueError("pixelFormat is not supported by this webcam")
            return self.params.get("pixelFormat", "UNKNOWN")

        if isinstance(value, (int, np.integer)):
            code = int(value)
        else:
            requested = str(value).upper()
            if autoCorrect and self._pixelFormatChoices and requested not in self._pixelFormatChoices:
                requested = self._pixelFormatChoices[0]
            if len(requested) != 4:
                if autoCorrect:
                    return self.params.get("pixelFormat", "UNKNOWN")
                raise ValueError("pixelFormat must be a 4-character FOURCC string")
            code = self._encodeFourcc(requested)

        prop_id = self._cv2Props["pixelFormat"]
        with self.camLock:
            ok = self._capture.set(prop_id, float(code))
            actual = int(round(self._capture.get(prop_id)))
        if not ok and not autoCorrect:
            raise ValueError(f"Failed to set pixelFormat to {value!r}")

        fmt = self._decodeFourcc(actual)
        self.params["pixelFormat"] = fmt
        if fmt not in self._pixelFormatChoices:
            self._pixelFormatChoices = [fmt] + [p for p in self._pixelFormatChoices if p != fmt]
            self.paramRanges["pixelFormat"] = (
                self._pixelFormatChoices,
                self.paramRanges["pixelFormat"][1],
                True,
                [],
            )
        return fmt

    def listParams(self, params=None):
        if params is None:
            return self.paramRanges.copy()
        if isinstance(params, str):
            return self.paramRanges[params]
        return {p: self.paramRanges[p] for p in params}

    def getParams(self, params=None):
        if params is None:
            params = list(self.paramRanges.keys())
        return {p: self.getParam(p) for p in params}

    def getParam(self, param):
        if param == "binning":
            return self.params["binningX"], self.params["binningY"]
        if param == "region":
            return (
                self.params["regionX"],
                self.params["regionY"],
                self.params["regionW"],
                self.params["regionH"],
            )
        if param == "sensorSize":
            return self._sensorSize
        if param in self._cv2Props and param != "pixelFormat":
            self.params[param] = self._readCv2Param(param)
            return self.params[param]
        if param == "pixelFormat" and param in self._cv2Props:
            with self.camLock:
                val = int(round(self._capture.get(self._cv2Props["pixelFormat"])))
            self.params["pixelFormat"] = self._decodeFourcc(val)
            return self.params["pixelFormat"]
        return self.params[param]

    def setParams(self, params: dict | list, autoRestart=True, autoCorrect=True):
        if isinstance(params, dict):
            params = list(params.items())

        newVals = {}
        for param, value in params:
            if param == "triggerMode":
                if value != "Normal" and not autoCorrect:
                    raise ValueError("WebcamCamera only supports triggerMode='Normal'")
                self.params["triggerMode"] = "Normal"
                newVals["triggerMode"] = "Normal"
                continue

            if param == "binning":
                x, y = int(value[0]), int(value[1])
                if (x, y) != (1, 1):
                    if not autoCorrect:
                        raise ValueError("WebcamCamera does not support binning")
                    x, y = 1, 1
                self.params["binningX"] = x
                self.params["binningY"] = y
                newVals["binningX"] = x
                newVals["binningY"] = y
                continue

            if param in ("binningX", "binningY"):
                v = int(value)
                if v != 1:
                    if not autoCorrect:
                        raise ValueError("WebcamCamera does not support binning")
                    v = 1
                self.params[param] = v
                newVals[param] = v
                continue

            if param == "region" or param.startswith("region"):
                # ROI is not supported; always force full frame.
                full = (0, 0, self.params["sensorSize"][0], self.params["sensorSize"][1])
                if param == "region":
                    req = tuple(int(v) for v in value)
                else:
                    req = list(full)
                    idx = {"regionX": 0, "regionY": 1, "regionW": 2, "regionH": 3}[param]
                    req[idx] = int(value)
                    req = tuple(req)
                if req != full and not autoCorrect:
                    raise ValueError("WebcamCamera does not support ROI changes")
                self.params["regionX"], self.params["regionY"], self.params["regionW"], self.params["regionH"] = full
                newVals.update(
                    {
                        "regionX": full[0],
                        "regionY": full[1],
                        "regionW": full[2],
                        "regionH": full[3],
                    }
                )
                continue

            if param == "exposure":
                lo, hi = self.paramRanges["exposure"][0]
                v = float(value)
                if autoCorrect:
                    v = min(max(v, lo), hi)
                elif v < lo or v > hi:
                    raise ValueError(f"exposure value out of range [{lo}, {hi}]")
                self.params["exposure"] = v
                newVals["exposure"] = v
                continue

            if param == "pixelFormat":
                newVals["pixelFormat"] = self._setFourcc(value, autoCorrect=autoCorrect)
                continue

            if param in self._cv2Props:
                newVals[param] = self._writeCv2Param(param, value, autoCorrect=autoCorrect)
                continue

            if param in self.params:
                if not autoCorrect:
                    raise ValueError(f"Parameter {param!r} is read-only")
                newVals[param] = self.params[param]
                continue

            raise KeyError(f"Unknown camera parameter {param!r}")

        if newVals:
            self.sigParamsChanged.emit(newVals)
        return newVals, False

    def _readCv2Param(self, param):
        prop_id = self._cv2Props[param]
        with self.camLock:
            val = self._capture.get(prop_id)
        if not np.isfinite(val):
            return self.params[param]
        if param in self._boolCv2Params:
            return bool(round(val))
        return float(val)

    def _writeCv2Param(self, param, value, autoCorrect=True):
        if param in self._boolCv2Params:
            target = bool(value)
            with self.camLock:
                ok = self._capture.set(self._cv2Props[param], float(int(target)))
            if not ok and not autoCorrect:
                raise ValueError(f"Failed to set parameter {param!r}")
            self.params[param] = self._readCv2Param(param)
            return self.params[param]

        target = float(value)
        spec = self.paramRanges.get(param, None)
        if spec is not None and isinstance(spec[0], tuple):
            lo, hi = spec[0][0], spec[0][1]
            if autoCorrect:
                target = min(max(target, lo), hi)
            elif target < lo or target > hi:
                raise ValueError(f"Parameter {param!r} out of range [{lo}, {hi}]")

        with self.camLock:
            ok = self._capture.set(self._cv2Props[param], target)
        if not ok and not autoCorrect:
            raise ValueError(f"Failed to set parameter {param!r}")
        self.params[param] = self._readCv2Param(param)
        return self.params[param]

    def startCamera(self):
        with self.camLock:
            if self._capture is None or not self._capture.isOpened():
                self._openCapture()

    def stopCamera(self):
        with self.camLock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None

    def newFrames(self):
        frames = []
        while True:
            try:
                frames.append(self.frameQueue.get_nowait())
            except queue.Empty:
                break
        return frames

    def _acquisitionLoop(self):
        while True:
            try:
                with self.camLock:
                    if self._capture is None:
                        ok = False
                        frame = None
                    else:
                        ok, frame = self._capture.read()
                now = ptime.time()
                if not ok or frame is None:
                    time.sleep(0.01)
                    continue
            except Exception:
                self.logger.exception("Error reading frame from webcam:")
                time.sleep(1.0)
                continue

            data = self._convertFrame(frame)
            self.params["bitDepth"] = int(data.dtype.itemsize * 8)
            out = {
                "id": self._frameId,
                "time": now,
                "data": data,
            }
            self.frameQueue.put(out)
            self._frameId += 1

    def _convertFrame(self, frame):
        if self._colorMode == "gray" and frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame.ndim == 2:
            return frame.T.copy()
        if frame.ndim == 3:
            return np.transpose(frame, (1, 0, 2)).copy()
        return np.ascontiguousarray(frame).copy()

    def _acquireFrames(self, n) -> np.ndarray:
        frames = []
        deadline = ptime.time() + 10.0
        while len(frames) < n:
            with self.camLock:
                if self._capture is None:
                    raise RuntimeError("Camera is not open")
                ok, frame = self._capture.read()
            if ok and frame is not None:
                frames.append(self._convertFrame(frame)[np.newaxis, ...])
                deadline = ptime.time() + 2.0
                continue
            if ptime.time() > deadline:
                raise TimeoutError("Timed out waiting for webcam frames")
            time.sleep(0.005)
        return np.concatenate(frames, axis=0)

    def quit(self):
        try:
            super().quit()
        finally:
            with self.camLock:
                if self._capture is not None:
                    self._capture.release()
                    self._capture = None
