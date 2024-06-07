import queue
import threading
import time
from collections import deque
from contextlib import contextmanager, ExitStack
from typing import Callable, Optional

import numpy as np
from MetaArray import MetaArray, axis

import acq4.util.ptime as ptime
import pyqtgraph as pg
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from acq4.devices.Device import Device
from acq4.devices.Microscope import Microscope
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
from acq4.util.future import Future
from acq4.util.imaging.frame import Frame
from pyqtgraph import Vector, SRTTransform3D
from pyqtgraph.debug import Profiler
from .CameraInterface import CameraInterface
from .deviceGUI import CameraDeviceGui
from .taskGUI import CameraTaskGui


class Camera(DAQGeneric, OptomechDevice):
    """Generic camera device class. All cameras should extend from this interface.
     - The class handles acquisition tasks, scope integration, expose/trigger lines
     - Subclasses should handle the connection to the camera driver by overriding
        listParams, getParams, and setParams.
     - Subclasses may need to create their own AcquireThread

    The list/get/setParams functions should implement a few standard items:
    (Note: these number values are just examples, but the data types and strings must be the same.)
        triggerMode:     str, ['Normal', 'TriggerStart', 'Strobe', 'Bulb']
        exposure:        float, (0.0, 10.0)
        binning:         (int,int) , [[1,2,4,8,16], [1,2,4,8,16]]
        region:          (int, int, int, int), [(0, 511), (0, 511), (1, 512), (1, 512)] #[x, y, w, h]
        gain:            float, (0.1, 10.0)

    The configuration for these devices should look like:
    (Note that each subclass will add config options for identifying the camera)
        scopeDevice: 'Microscope'
        scaleFactor: (1.0, 1.0)  # used for rectangular pixels
        exposeChannel: 'DAQ', '/Dev1/port0/line14'  # Channel for recording expose signal
        triggerOutChannel: 'DAQ', '/Dev1/PFI5'  # Channel the DAQ should trigger off of to sync with camera
        triggerInChannel: 'DAQ', '/Dev1/port0/line13'  # Channel the DAQ should raise to trigger the camera
        params:
            GAIN_INDEX: 2
            CLEAR_MODE: 'CLEAR_PRE_SEQUENCE'  # Overlap mode for QuantEM
    """

    sigCameraStopped = Qt.Signal()
    sigCameraStarted = Qt.Signal()
    sigShowMessage = Qt.Signal(object)  # (string message)
    sigNewFrame = Qt.Signal(object)  # (frame data)
    sigParamsChanged = Qt.Signal(object)

    def __init__(self, dm, config, name):
        # Generate config to use for DAQ
        daqConfig = {}
        if "exposeChannel" in config:
            daqConfig["exposure"] = config["exposeChannel"]
        if "triggerInChannel" in config:
            daqConfig["trigger"] = config["triggerInChannel"]
        DAQGeneric.__init__(self, dm, daqConfig, name)
        OptomechDevice.__init__(self, dm, config, name)

        self.lock = Mutex(Mutex.Recursive)

        self.camConfig = config
        self.stateStack = []

        if "scaleFactor" not in self.camConfig:
            self.camConfig["scaleFactor"] = [1.0, 1.0]

        # Default values for scope state. These will be used if there is no scope defined.
        self.scopeState = {}

        self.scopeDev = None
        p = self
        while p is not None:
            p = p.parentDevice()
            if isinstance(p, Microscope):
                self.scopeDev = p
                self.scopeDev.sigObjectiveChanged.connect(self.objectiveChanged)
                self.scopeDev.sigLightChanged.connect(self._lightChanged)
                break

        self.transformChanged()
        if self.scopeDev is not None:
            self.objectiveChanged()
            self._lightChanged()

        self.setupCamera()
        self.sensorSize = self.getParam("sensorSize")
        tr = pg.SRTTransform3D()
        tr.translate(-self.sensorSize[0] * 0.5, -self.sensorSize[1] * 0.5)
        self.setDeviceTransform(self.deviceTransform() * tr)
        self._frameInfoUpdater = None

        self.acqThread = AcquireThread(self)
        self.acqThread.finished.connect(self.acqThreadFinished)
        self.acqThread.started.connect(self.acqThreadStarted)
        self.acqThread.sigShowMessage.connect(self.showMessage)

        self._processingThread = FrameProcessingThread()
        self._processingThread.sigFrameFullyProcessed.connect(self.sigNewFrame)
        self._processingThread.start()
        self._processingThread.addFrameProcessor(self.addFrameInfo)

        self.sigGlobalTransformChanged.connect(self.transformChanged)

        if config != None:
            # look for 'defaults', then 'params' to preserve backward compatibility.
            defaults = config.get("defaults", config.get("params", {}))
            try:
                self.setParams(defaults)
            except:
                printExc("Error default setting camera parameters:")

        # set up preset hotkeys
        for presetName, preset in self.camConfig.get("presets", {}).items():
            if "hotkey" not in preset:
                continue
            dev = dm.getDevice(preset["hotkey"]["device"])
            key = preset["hotkey"]["key"]
            dev.addKeyCallback(key, self.presetHotkeyPressed, (presetName,))

        dm.declareInterface(name, ["camera"], self)

    def devicesToReserve(self) -> list[Device]:
        return self.parentDevices()

    def addFrameInfo(self, frame: Frame):
        if self._frameInfoUpdater is None:
            self._frameInfoUpdater = self._makeFrameInfoUpdater(frame.info().copy())
        self._frameInfoUpdater(frame)

    def _makeFrameInfoUpdater(self, templateInfo):
        scope_state = self.getScopeState()
        dev_xform = pg.SRTTransform3D(scope_state["transform"])
        ps = scope_state["pixelSize"]  # size of CCD pixel

        def _update(frame):
            info = frame.info().copy()

            cam_params = {"binning", "exposure", "region", "triggerMode"}
            if cam_params - info.keys():
                info.update(dict(self.getParams(cam_params)))

            binning = info["binning"]
            frame_xform = self.makeFrameTransform(info["region"], binning)
            new_info = {
                "deviceName": self.name(),
                "pixelSize": [ps[0] * binning[0], ps[1] * binning[1]],  # size of image pixel
                "objective": scope_state.get("objective", None),
                "deviceTransform": dev_xform,
                "illumination": scope_state.get("illumination", None),
                "frameTransform": frame_xform,
                "transform": SRTTransform3D(dev_xform * frame_xform),
            }

            frame.addInfo(new_info)

        return _update

    def setupCamera(self):
        """Prepare the camera at least so that get/setParams will function correctly"""
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def listParams(self, params=None):
        """Return a dictionary of parameter descriptions. By default, all parameters are listed.
        Each description is a tuple or list: (values, isWritable, isReadable, dependencies)
        
        values may be any of:
          - Tuple of ints or floats indicating minimum and maximum values
          - List of int / float / string values
          - Tuple of strings, indicating that the parameter is made up of multiple sub-parameters
             (eg, 'region' should be ('regionX', 'regionY', 'regionW', 'regionH')
             
        dependencies is a list of other parameters which affect the allowable values of this parameter.
        
        eg:
        {  'paramName': ([list of values], True, False, []) }
        """
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        """Set camera parameters. Options are:
           params: a list or dict of (param, value) pairs to be set. Parameters are set in the order specified.
           autoRestart: If true, restart the camera if required to enact the parameter changes
           autoCorrect: If true, correct values that are out of range to their nearest acceptable value
        
        Return a tuple with: 
           0: dictionary of parameters and the values that were set.
              (note this may differ from requested values if autoCorrect is True)
           1: Boolean value indicating whether a restart is required to enact changes.
              If autoRestart is True, this value indicates whether the camera was restarted."""
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def getParams(self, params=None):
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def setParam(self, param, val, autoCorrect=True, autoRestart=True):
        return self.setParams([(param, val)], autoCorrect=autoCorrect, autoRestart=autoRestart)[0]

    def getParam(self, param):
        return self.getParams([param])[param]

    def listPresets(self):
        """Return a list of all preset names.
        """
        return list(self.camConfig.get("presets", {}).keys())

    def loadPreset(self, preset):
        presets = self.camConfig.get("presets", None)
        if presets is None or preset not in presets:
            raise ValueError("No camera preset named %r" % preset)
        params = presets[preset]["params"]
        self.setParams(params)

    def presetHotkeyPressed(self, dev, changes, presetName):
        self.loadPreset(presetName)

    def newFrames(self):
        """Returns a list of all new frames that have arrived since the last call. The list looks like:
            [{'id': 0, 'data': array, 'time': 1234678.3213}, ...]
        id is a unique integer representing the frame number since the start of the program.
        data should be a permanent copy of the image (ie, not directly from a circular buffer)
        time is the time of arrival of the frame. Optionally, 'exposeStartTime' and 'exposeDoneTime' 
            may be specified if they are available.
        """
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def startCamera(self):
        """Calls the camera driver to start the camera's acquisition. Call start instead of this to actually record frames."""
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def stopCamera(self):
        """Calls the camera driver to stop the camera's acquisition.
        Note that the acquisition may be _required_ to stop, since other processes
        may be preparing to synchronize with the camera's exposure signal."""
        raise NotImplementedError("Function must be reimplemented in subclass.")

    def noFrameWarning(self, time):
        # display a warning message that no camera frames have arrived.
        # This method is only here to allow PVCam to display some useful information.
        print("Camera acquisition thread has been waiting %02f sec but no new frames have arrived; shutting down." % time)
    
    def pushState(self, name=None, params=None):
        if params is None:
            # push all writeable parameters
            params = [param for param, spec in self.listParams().items() if spec[1] is True]

        params = self.getParams(params)
        params["isRunning"] = self.isRunning()
        self.stateStack.append((name, params))

    def popState(self, name=None):
        if name is None:
            state = self.stateStack.pop()[1]
        else:
            inds = [i for i in range(len(self.stateStack)) if self.stateStack[i][0] == name]
            if len(inds) == 0:
                raise Exception("Can not find camera state named '%s'" % name)
            state = self.stateStack[inds[-1]][1]
            self.stateStack = self.stateStack[: inds[-1]]

        run = state["isRunning"]
        del state["isRunning"]
        nv, restart = self.setParams(state, autoRestart=False)

        if self.isRunning():
            if run:
                if restart:
                    self.restart()
            else:
                self.stop()
        else:
            if run:
                self.start()

    def start(self, block=True):
        """Start camera and acquisition thread"""
        self.acqThread.start(block=block)

    def stop(self, block=True):
        """Stop camera and acquisition thread. If block is True, this is not safe to call on an
        already-stopped camera."""
        self.acqThread.stop(block=block)

    @contextmanager
    def ensureRunning(self, ensureFreshFrames=False):
        """Context manager for starting and stopping camera acquisition thread. If used
        with non-blocking frame acquisition, this will still exit the context before
        the frames are necessarily acquired.

        Usage::
            with camera.ensureRunning():
                frames = camera.acquireFrames(10).getResult()
        """
        running = self.isRunning()
        if ensureFreshFrames:
            if running:
                self.stop()
                # todo sleep until all frames are cleared somehow?
                self.start()
        if not running:
            self.start()
        try:
            yield
        finally:
            if not running:
                self.stop()

    def acquireFrames(self, n=None, ensureFreshFrames=False) -> "FrameAcquisitionFuture":
        """Acquire a specific number of frames and return a FrameAcquisitionFuture.

        If *n* is None, then frames will be acquired until future.stop() is called.
        Call future.getResult() to return the acquired Frame object.

        This method works by collecting frames as they stream from the camera and does not
        handle starting / stopping / configuring the camera.
        """
        if n is None and ensureFreshFrames:
            raise ValueError("ensureFreshFrames=True is not compatible with n=None")
        return FrameAcquisitionFuture(self, n, ensureFreshFrames=ensureFreshFrames)

    @Future.wrap
    def driverSupportedFixedFrameAcquisition(self, n: int = 1, _future: Future = None) -> list["Frame"]:
        """Ask the camera driver to acquire a specific number of frames and return a Future.

        Call future.getResult() to return the acquired Frame object.

        Depending on the underlying camera driver, this method may cause the camera to restart.
        """
        frames = self._acquireFrames(n)
        now = ptime.time()
        frames = [Frame(f, {"time": now}) for f in frames]
        for f in frames:
            # allow others access to this frame (for example, camera module can update)
            self._processingThread.handleNewRawFrame(f)
        return frames

    def _acquireFrames(self, n) -> np.ndarray:
        # todo: default implementation can use acquisition thread instead..
        raise NotImplementedError(f"Camera class {self.__class__.__name__} does not implement this method.")

    def restart(self):
        if self.isRunning():
            self.stop()
            self.start()

    def quit(self):
        if hasattr(self, "acqThread") and self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise TimeoutError("Timed out while waiting for acquisition thread to exit!")
        if hasattr(self, "_processingThread") and self._processingThread.isRunning():
            self._processingThread.stop()
            if not self._processingThread.wait(10000):
                raise TimeoutError("Timed out waiting for frame processing thread to stop")
        DAQGeneric.quit(self)

    @Future.wrap
    def getEstimatedFrameRate(self, _future: Future):
        """Return the estimated frame rate of the camera.
        """
        with self.ensureRunning():
            return _future.waitFor(self.acqThread.getEstimatedFrameRate()).getResult()

    # @ftrace
    def createTask(self, cmd, parentTask):
        with self.lock:
            return CameraTask(self, cmd, parentTask)

    # @ftrace
    def getTriggerChannels(self, daq: str):
        chans = {'input': None, 'output': None}
        if "triggerOutChannel" in self.camConfig and self.camConfig["triggerOutChannel"]["device"] == daq:
            chans['input'] = self.camConfig["triggerOutChannel"]['channel']
        if "triggerInChannel" in self.camConfig and self.camConfig["triggerInChannel"]["device"] == daq:
            chans['output'] = self.camConfig["triggerInChannel"]['channel']
        return chans

    def getExposureChannel(self):
        return self.camConfig.get('exposeChannel', None)

    def taskInterface(self, taskRunner):
        return CameraTaskGui(self, taskRunner)

    def deviceInterface(self, win):
        return CameraDeviceGui(self, win)

    def cameraModuleInterface(self, mod):
        return CameraInterface(self, mod)

    # Scope interface functions below

    # @ftrace
    def getPixelSize(self):
        """Return the absolute size of 1 pixel"""
        with self.lock:
            return self.scopeState["pixelSize"]

    # @ftrace
    def getObjective(self):
        with self.lock:
            return self.scopeState["objective"]

    def getScopeDevice(self):
        with self.lock:
            return self.scopeDev

    def getBoundary(self, globalCoords: bool = True, mode="sensor") -> tuple:
        """Return the boundaries of the camera in the specified coordinates.
        If globalCoords is False, return in local coordinates.
        `mode` can be either "sensor" for max sensor size or "roi" for current available region.
        Returns (left, top, width, height).
        """
        if mode == "sensor":
            bounds = (0, 0, *self.getParam("sensorSize"))
        elif mode == "roi":
            bounds = self.getParam("region")
        else:
            raise ValueError("mode must be either 'sensor' or 'roi'")
        bounds = tuple(map(float, bounds))
        if globalCoords:
            start = self.mapToGlobal(bounds[:2])
            end = self.mapToGlobal((bounds[2] + bounds[0], bounds[3] + bounds[1]))
            size = (end[0] - start[0], end[1] - start[1])
            return (*start, *size)
        else:
            return bounds

    def getScopeState(self):
        """Return meta information to be included with each frame. This function must be FAST."""
        with self.lock:
            return self.scopeState

    def transformChanged(self):  # called when this device's global transform changes.
        prof = Profiler(disabled=True)
        self.scopeState["transform"] = self.globalTransform()
        o = Vector(self.scopeState["transform"].map(Vector(0, 0, 0)))
        p = Vector(self.scopeState["transform"].map(Vector(1, 1)) - o)
        self.scopeState["centerPosition"] = o
        self.scopeState["pixelSize"] = np.abs(p)
        self._frameInfoUpdater = None

    def globalCenterPosition(self, mode="sensor"):
        """Return the global position of the center of the camera sensor (mode='sensor') or ROI (mode='roi').
        """
        if mode == "sensor":
            size = self.getParam("sensorSize")
            center = np.array(list(size) + [0]) / 2.0
        elif mode == "roi":
            rgn = self.getParam("region")
            center = np.array([rgn[0] + rgn[2] / 2.0, rgn[1] + rgn[3] / 2.0, 0])
        else:
            raise ValueError("mode argument must be 'sensor' or 'roi'")

        return self.mapToGlobal(center)

    def moveCenterToGlobal(self, position, speed, center="roi"):
        """Move this camera's stage such that its center is focused on a given global position.

        The center to focus may be either the 'sensor' or the 'roi'.
        """
        scope = self.scopeDev
        camCenter = np.array(self.globalCenterPosition(center))
        scopeCenter = np.array(pg.Vector(scope.globalPosition()))

        scopePos = scopeCenter + np.array(position) - camCenter
        return scope.setGlobalPosition(scopePos, speed=speed)

    def getFocusDepth(self):
        """Return the z-position of the focal plane.
        """
        return self.mapToGlobal(Qt.QVector3D(0, 0, 0)).z()

    def setFocusDepth(self, z, speed='fast'):
        """Set the z-position of the focal plane by moving the parent focusing device.
        """
        # this is how much the focal plane needs to move (in the global frame)
        dif = z - self.getFocusDepth()
        scopez = self.scopeDev.getFocusDepth() + dif
        return self.scopeDev.setFocusDepth(scopez, speed)

    def objectiveChanged(self, obj=None):
        if obj is None:
            obj = self.scopeDev.getObjective()
        else:
            obj, oldObj = obj
        with self.lock:
            self.scopeState["objective"] = obj.name()
            self._frameInfoUpdater = None

    def _lightChanged(self):
        with self.lock:
            if self.scopeDev.lightSource is None:
                return
            self.scopeState["illumination"] = self.scopeDev.lightSource.describe()
            self._frameInfoUpdater = None

    @staticmethod
    def makeFrameTransform(region, binning):
        """Make a transform that maps from image coordinates to whole-sensor coordinates,
        given the region-of-interest and binning used to acquire the image."""
        tr = SRTTransform3D()
        tr.translate(*region[:2])
        tr.scale(binning[0], binning[1], 1)
        return tr

    # Proxy signals and functions for acqThread:
    ############################################

    def acqThreadFinished(self):
        self.sigCameraStopped.emit()

    def acqThreadStarted(self):
        self.sigCameraStarted.emit()

    def showMessage(self, msg):
        self.sigShowMessage.emit(msg)

    def addFrameProcessor(self, processor: Callable[[Frame], None], final: bool = False):
        self._processingThread.addFrameProcessor(processor, final)
        # TODO will we remove them ever?

    def isRunning(self):
        return self.acqThread.isRunning()

    def wait(self, *args, **kargs):
        return self.acqThread.wait(*args, **kargs)


class CameraTask(DAQGenericTask):
    def __init__(self, dev: Camera, cmd, parentTask):
        daqCmd = {}
        if "channels" in cmd:
            daqCmd = cmd["channels"]
        DAQGenericTask.__init__(self, dev, daqCmd, parentTask)

        self.__startOrder = [], []
        self.camCmd = cmd
        self.lock = Mutex()
        self.recordHandle = None
        self._dev_needs_restart = False
        self.stopRecording = False
        self._stopTime = 0
        self.resultObj = None
        self._future = None

    def configure(self):
        # Merge command into default values:
        prof = Profiler("Camera.CameraTask.configure", disabled=True)

        # set default parameters, load params from command
        params = {
            "triggerMode": "Normal",
        }
        params.update(self.camCmd["params"])

        # If we are sending a one-time trigger to start the camera, then it must be restarted to arm the trigger
        # (bulb and strobe modes only require a restart if the trigger mode is not already set; this is handled later)
        restart = False
        if params["triggerMode"] == "TriggerStart":
            restart = True

        # If the DAQ is triggering the camera, then the camera must start before the DAQ
        if params["triggerMode"] != "Normal":
            if 'triggerInChannel' in self.dev.camConfig:
                daqName = self.dev.camConfig["triggerInChannel"]["device"]
                self.__startOrder[1].append(daqName)

            # Make sure we haven't requested something stupid..
            if (
                self.camCmd.get("triggerProtocol", False)
                and self.dev.camConfig["triggerOutChannel"]["device"] == daqName
            ):
                raise Exception("Task requested camera to trigger and be triggered by the same device.")

        if "pushState" in self.camCmd:
            stateName = self.camCmd["pushState"]
            self.dev.pushState(stateName, params=list(params.keys()))
        prof.mark("push params onto stack")

        (newParams, paramsNeedRestart) = self.dev.setParams(
            params, autoCorrect=True, autoRestart=False
        )  # we'll restart in a moment if needed..
        restart = restart or paramsNeedRestart
        prof.mark("set params")

        # If the camera is triggering the daq, stop acquisition now and request that it starts after the DAQ
        #   (daq must be started first so that it is armed to received the camera trigger)
        if self.camCmd.get("triggerProtocol", False):
            assert 'triggerOutChannel' in self.dev.camConfig, f"Task requests {self.dev.name()} to trigger the protocol to start, "\
                                                              "but no trigger lines are configured ('triggerOutChannel' needed in config)"
            restart = True
            daqName = self.dev.camConfig["triggerOutChannel"]["device"]
            self.__startOrder = [daqName], []
            prof.mark("conf 1")

        if self.fixedFrameCount is not None:
            restart = restart or self.dev.isRunning()

        # We want to avoid this if at all possible since it may be very expensive
        self._dev_needs_restart = restart
        if restart and self.dev.isRunning():
            self.dev.stop(block=True)
        prof.mark("stop")

        if self.fixedFrameCount is None:
            self._future = self.dev.acquireFrames(n=self.fixedFrameCount)

        # Call the DAQ configure
        DAQGenericTask.configure(self)
        prof.mark("DAQ configure")
        prof.finish()

    @property
    def fixedFrameCount(self):
        return self.camCmd.get("minFrames", None)

    def getStartOrder(self):
        order = DAQGenericTask.getStartOrder(self)
        return order[0] + self.__startOrder[0], order[1] + self.__startOrder[1]

    def start(self):
        # arm recording
        self.stopRecording = False
        if self.fixedFrameCount is not None:
            self._future = self.dev.driverSupportedFixedFrameAcquisition(n=self.fixedFrameCount)
        elif not self.dev.isRunning():
            self.dev.start(block=True)

        # Last I checked, this does nothing. It should be here anyway, though..
        DAQGenericTask.start(self)

    def isDone(self):
        # If camera stopped, then probably there was a problem and we are finished.
        return self._future.isDone() or self._stopTime is not None or not self.dev.isRunning()

    def stop(self, abort=False):
        """Warning: this won't stop everything and you'll also need to call *getResult* within the
        containing device-reservation context to get the proper result.
        """
        # Stop DAQ first
        DAQGenericTask.stop(self, abort=abort)

        with self.lock:
            self.stopRecording = True
            self._stopTime = time.time()
            self.dev.stopCamera()
            if self.fixedFrameCount is None:
                self._future.stopWhen(lambda frame: frame.info()["time"] >= self._stopTime, blocking=False)

        if "popState" in self.camCmd:
            self.dev.popState(self.camCmd["popState"])  # restores previous settings, stops/restarts camera if needed

    def getResult(self):
        if self.resultObj is None:
            daqResult = DAQGenericTask.getResult(self)
            while time.time() - self._stopTime < 1 and not self._future.isDone():
                # Wait up to 1 second for all frames to arrive from camera thread before returning results.
                # In some cases, acquisition thread can get bogged down and we may need to wait for it
                # to catch up.
                time.sleep(0.05)
            self._future.stop()  # TODO this could error for fixedFrameCount!=None
            self.resultObj = CameraTaskResult(self, self._future.getResult(timeout=1), daqResult)
            if self._dev_needs_restart:
                self.dev.start(block=False)
                self._dev_needs_restart = False
        return self.resultObj

    def storeResult(self, dirHandle):
        result = self.getResult()
        result = {"frames": (result.asMetaArray(), result.info()), "daqResult": (result.daqResult(), {})}
        dh = dirHandle.mkdir(self.dev.name())
        for k in result:
            data, info = result[k]
            if data is not None:
                dh.writeFile(data, k, info=info)


class CameraTaskResult:
    def __init__(self, task, frames, daqResult):
        self.lock = Mutex(recursive=True)
        self._task = task
        self._frames = frames
        self._daqResult = daqResult
        self._marr = None
        self._arr = None
        self._frameTimes = None
        self._frameTimesPrecise = False

    def frames(self):
        """Return a list of Frame instances collected during the task"""
        return self._frames[:]

    def info(self):
        """Return meta-info for the first frame recorded or {} if there were no frames."""
        if len(self._frames) == 0:
            return {}
        info = self._frames[0].info().copy()
        info.update({"preciseTiming": self._frameTimesPrecise})
        return info

    def asArray(self):
        with self.lock:
            if self._arr is None:
                if len(self._frames) > 0:
                    self._arr = np.concatenate([f.data()[np.newaxis, ...] for f in self._frames])
        return self._arr

    def asMetaArray(self):
        """Return a MetaArray containing all frame and timing data"""
        with self.lock:
            if self._marr is None:
                arr = self.asArray()
                if arr is not None:
                    times, precise = self.frameTimes()
                    times = times[: arr.shape[0]]
                    info = [axis(name="Time", units="s", values=times), axis(name="x"), axis(name="y"), self.info()]
                    self._marr = MetaArray(arr, info=info)

        return self._marr

    def daqResult(self):
        """Return results of DAQ channel recordings"""
        return self._daqResult

    def frameTimes(self):
        if self._frameTimes is None:
            # generate MetaArray of images collected during recording
            times = None
            precise = False  # becomes True if we are able to determine precise frame times.
            with self.lock:
                if len(self._frames) > 0:  # extract frame times as reported by camera. This is a first approximation.
                    try:
                        times = np.array([f.info()["time"] for f in self._frames])
                    except:
                        raise
                    times -= times[0]
                else:
                    return None, False

                expose = None
                daqResult = self._daqResult
                if daqResult is not None and daqResult.hasColumn("Channel", "exposure"):
                    expose = daqResult["Channel":"exposure"]

            # Correct times for each frame based on data recorded from exposure channel.
            if expose is not None:

                # Extract times from trace
                ex = expose.view(np.ndarray).astype(np.int32)
                exd = ex[1:] - ex[:-1]

                timeVals = expose.xvals("Time")
                inds = np.argwhere(exd > 0.5)[:, 0] + 1
                onTimes = timeVals[inds]

                # If camera triggered DAQ, then it is likely we missed the first 0->1 transition
                if self._task.camCmd.get("triggerProtocol", False) and ex[0] > 0.5:
                    onTimes = np.array([timeVals[0]] + list(onTimes))

                inds = np.argwhere(exd < 0.5)[:, 0] + 1
                offTimes = timeVals[inds]

                # Determine average frame transfer time
                txLen = (offTimes[: len(times)] - times[: len(offTimes)]).mean()

                # Determine average exposure time (excluding first frame, which is often shorter)
                expLen = (offTimes[1 : len(onTimes)] - onTimes[1 : len(offTimes)]).mean()

                if self._task.camCmd["params"].get("triggerMode", "Normal") == "Normal" and not self._task.camCmd.get(
                    "triggerProtocol", False
                ):
                    # Can we make a good guess about frame times even without having triggered the first frame?
                    # frames are marked with their arrival time. We will assume that a frame most likely
                    # corresponds to the last complete exposure signal.
                    pass

                elif len(onTimes) > 0:
                    # If we triggered the camera (or if the camera triggered the DAQ),
                    # then we know frame 0 occurred at the same time as the first expose signal.
                    # New times list is onTimes, any extra frames just increment by tx+exp time
                    times[: len(onTimes)] = onTimes[
                        : len(times)
                    ]  # set the times for which we detected an exposure pulse

                    # Try to determine mean framerate
                    if len(onTimes) > 1:
                        framePeriod = (onTimes[-1] - onTimes[0]) / (len(onTimes) - 1)
                    else:
                        framePeriod = (times[-1] - times[0]) / (len(times) - 1)

                    # For any extra frames that did not have an exposure signal, just try
                    # to guess the correct time based on the average framerate.
                    lastTime = onTimes[-1]
                    if framePeriod is not None:
                        for i in range(len(onTimes), len(times)):
                            lastTime += framePeriod
                            times[i] = lastTime

                    precise = True

            self._frameTimes = times
            self._frameTimesPrecise = precise

        return self._frameTimes, self._frameTimesPrecise


class FrameProcessingThread(Thread):
    sigFrameFullyProcessed = Qt.Signal(object)  # Frame

    def __init__(self):
        super().__init__()
        self._stop = False
        self._processors = []
        self._final_processor = None
        self._queue = queue.Queue()

    def addFrameProcessor(self, processor: Callable[[Frame], None], final=False):
        if final:
            if self._final_processor is not None:
                raise RuntimeError("Only one `final` processor can be added.")
            self._final_processor = processor
        else:
            self._processors.append(processor)

    def stop(self):
        self._stop = True

    @property
    def processors(self):
        if self._final_processor is not None:
            return self._processors + [self._final_processor]
        return self._processors

    def handleNewRawFrame(self, frame):
        self._queue.put(frame)

    def run(self):
        while not self._stop:
            try:
                frame = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            for callback in self.processors:
                try:
                    callback(frame)
                except Exception:
                    printExc("Frame processing callback failed")
            self.sigFrameFullyProcessed.emit(frame)


class AcquireThread(Thread):
    sigShowMessage = Qt.Signal(object)

    def __init__(self, dev: Camera):
        Thread.__init__(self)
        self.dev = dev
        self.camLock = self.dev.camLock
        self.stopThread = False
        self.lock = Mutex()
        self.acqBuffer = None
        self.bufferTime = 5.0
        self.tasks = []
        self.cameraStartEvent = threading.Event()
        self._recentFPS = deque(maxlen=10)

    def __del__(self):
        if hasattr(self, "cam"):
            self.dev.stopCamera()

    def start(self, *args, block=True):
        self.cameraStartEvent.clear()
        self.lock.lock()
        self.stopThread = False
        self.lock.unlock()
        Thread.start(self, *args)
        if block:
            if not self.cameraStartEvent.wait(5):
                raise TimeoutError("Timed out waiting for camera to start.")

    def run(self):
        lastFrameId = None

        camState = dict(self.dev.getParams(["binning", "exposure", "region", "triggerMode"]))
        exposure = camState["exposure"]
        mode = camState["triggerMode"]

        try:
            self.dev.startCamera()
            self.cameraStartEvent.set()

            lastFrameTime = lastStopCheck = ptime.time()
            frameInfo = {}

            while True:
                now = ptime.time()
                frames = self.dev.newFrames()

                # If a new frame is available, process it and inform other threads
                if len(frames) > 0:
                    if lastFrameId is not None:
                        drop = frames[0]["id"] - lastFrameId - 1
                        if drop > 0:
                            print(f"WARNING: Camera dropped {drop} frames")

                    # Build meta-info for this frame(s)
                    info = camState.copy()

                    # Process all waiting frames. If there is more than one frame waiting, guess the frame times.
                    dt = (now - lastFrameTime) / len(frames)
                    if dt > 0:
                        info["fps"] = 1.0 / dt
                        self._recentFPS.append(info["fps"])
                    else:
                        info["fps"] = None

                    for frame in frames:
                        frameInfo = info.copy()
                        data = frame.pop("data")
                        frameInfo.update(frame)  # copies 'time' key supplied by camera
                        f = Frame(data, frameInfo)
                        self.dev._processingThread.handleNewRawFrame(f)

                    lastFrameTime = now
                    lastFrameId = frames[-1]["id"]

                time.sleep(1e-3)

                # check for stop request every 10ms
                if now - lastStopCheck > 10e-3:
                    lastStopCheck = now

                    # If no frame has arrived yet, do NOT allow the camera to stop (this can hang the driver)   << bug should be fixed in pvcam driver, not here.
                    self.lock.lock()
                    if self.stopThread:
                        self.stopThread = False
                        self.lock.unlock()
                        break
                    self.lock.unlock()

                    diff = ptime.time() - lastFrameTime
                    if diff > (10 + exposure):
                        if mode == "Normal":
                            self.dev.noFrameWarning(diff)
                            break
                        else:
                            pass  # do not exit loop if there is a possibility we are waiting for a trigger

            with self.camLock:
                self.dev.stopCamera()
        except:
            printExc("Error starting camera acquisition:")
            try:
                with self.camLock:
                    self.dev.stopCamera()
            except:
                pass
            self.sigShowMessage.emit("ERROR starting acquisition (see console output)")

    @Future.wrap
    def getEstimatedFrameRate(self, _future: Future = None):
        """Return the estimated frame rate of the camera.
        """
        if not self.isRunning():
            raise RuntimeError("Cannot get frame rate while camera is not running.")
        while len(self._recentFPS) < self._recentFPS.maxlen:
            time.sleep(0.01)
            _future.checkStop()
        return np.mean(self._recentFPS)

    def stop(self, block=False):
        with self.lock:
            self.stopThread = True
        if block:
            if not self.wait(10000):
                raise Exception("Timed out waiting for thread exit!")
        self._recentFPS.clear()

    def reset(self):
        if self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
            self.start()


class FrameAcquisitionFuture(Future):
    def __init__(
            self,
            camera: Camera,
            frameCount: Optional[int],
            timeout: float = 10,
            ensureFreshFrames: bool = False,
    ):
        """Acquire a frames asynchronously, either a fixed number or continuously until stopped."""
        super().__init__()
        self._camera = camera
        self._frame_count = frameCount
        self._ensure_fresh_frames = ensureFreshFrames
        self._stop_when = None
        self._frames = []
        self._timeout = timeout
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._monitorAcquisition, daemon=True)
        self._thread.start()

    def _monitorAcquisition(self):
        self._camera.sigNewFrame.connect(self._queue.put, type=Qt.Qt.DirectConnection)
        with ExitStack() as stack:
            stack.callback(self._camera.sigNewFrame.disconnect, self._queue.put)
            if self._ensure_fresh_frames:
                stack.enter_context(self._camera.ensureRunning(ensureFreshFrames=True))
            lastFrameTime = ptime.time()
            while True:
                if self.isDone():
                    break
                try:
                    frame = self._queue.get_nowait()
                    lastFrameTime = ptime.time()
                except queue.Empty:
                    try:
                        self.checkStop(0.1)  # delay while checking for a stop request
                    except self.StopRequested:
                        self._taskDone(interrupted=self._frame_count is not None)
                        break
                    if ptime.time() - lastFrameTime > self._timeout:
                        self._taskDone(interrupted=True, error=TimeoutError("Timed out waiting for frames"))
                        break
                    continue
                self._frames.append(frame)
                if self._stop_when is not None and self._stop_when(frame):
                    self._taskDone()
                    break
                if self._frame_count is not None and len(self._frames) >= self._frame_count:
                    self._taskDone()
                    break

    def peekAtResult(self) -> list[Frame]:
        return self._frames[:]

    def getResult(self, timeout=None) -> list[Frame]:
        if timeout is None and self._frame_count is None and not self.isDone():
            raise ValueError("Must specify a timeout when still acquiring an unlimited number of frames.")
        self.wait(timeout)
        return self._frames

    def stopWhen(self, condition: Callable[[Frame], bool], blocking=True) -> None:
        """Stop acquiring frames when the given condition returns True.
        If blocking is True, then this method will not return until the condition is met.
        """
        if self._frame_count is not None:
            raise ValueError("Cannot stopWhen() when acquiring a fixed number of frames.")
        self._stop_when = condition
        if blocking:
            self.wait()

    def percentDone(self):
        if self._frame_count is None:
            return 0
        return len(self._frames) / self._frame_count
