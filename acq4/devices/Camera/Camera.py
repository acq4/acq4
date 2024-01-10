import queue
from collections import deque

import numpy as np
import threading
import time

from typing import Callable, Optional
from contextlib import contextmanager, ExitStack
from six.moves import range

import pyqtgraph as pg
from MetaArray import MetaArray, axis
import acq4.util.ptime as ptime
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from acq4.devices.Microscope import Microscope
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.util import Qt, imaging
from acq4.util.future import Future
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.util.debug import printExc
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
        self.scopeState = {
            "id": 0,
        }

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

        self.acqThread = AcquireThread(self)
        self.acqThread.finished.connect(self.acqThreadFinished)
        self.acqThread.started.connect(self.acqThreadStarted)
        self.acqThread.sigShowMessage.connect(self.showMessage)
        self.acqThread.sigNewFrame.connect(self.newFrame)

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

        self._multiprocessingHandler = MultiprocessCameraWorkers(self, config)
        dm.declareInterface(name, ["camera"], self)

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
            with camera.run():
                frames = camera.acquireFrames(10, blocking=True)
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
        frames = self._acquireFrames(int(n))

        info = self.acqThread.buildFrameInfo(self.getScopeState())
        info["time"] = ptime.time()
        retval = []
        for f in frames:
            retval.append(Frame(f, info))
            self.newFrame(retval[-1])  # allow others access to this frame (for example, camera module can update)
        return retval

    def _acquireFrames(self, n):
        # todo: default implementation can use acquisition thread instead..
        raise NotImplementedError("Camera class %s does not implement this method." % self.__class__.__name__)

    def restart(self):
        if self.isRunning():
            self.stop()
            self.start()

    def quit(self):
        if hasattr(self, "acqThread") and self.isRunning():
            self.stop()
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
        self._multiprocessingHandler.quit()
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

    def getBoundary(self, globalCoords=True):
        """Return the boundaries of the camera sensor in global coordinates.
        If globalCoords==False, return in local coordinates.
        """
        size = self.getParam("sensorSize")
        bounds = Qt.QPainterPath()
        bounds.addRect(Qt.QRectF(0, 0, *size))
        if globalCoords:
            return pg.SRTTransform(self.globalTransform()).map(bounds)
        else:
            return bounds

    def getBoundaries(self):
        """Return a list of camera boundaries for all objectives"""
        objs = self.scopeDev.listObjectives()
        return [self.getBoundary(o) for o in objs]

    # deprecated: not used anywhere, and I'm not sure it's correct.
    # def mapToSensor(self, pos):
    #     """Return the sub-pixel location on the sensor that corresponds to global position pos"""
    #     ss = self.getScopeState()
    #     boundary = self.getBoundary()
    #     boundary.translate(*ss['scopePosition'][:2])
    #     size = self.sensorSize
    #     x = (pos[0] - boundary.left()) * (float(size[0]) / boundary.width())
    #     y = (pos[1] - boundary.top()) * (float(size[1]) / boundary.height())
    #     return (x, y)

    def getScopeState(self):
        """Return meta information to be included with each frame. This function must be FAST."""
        with self.lock:
            return self.scopeState

    def transformChanged(self):  # called then this device's global transform changes.
        prof = Profiler(disabled=True)
        self.scopeState["transform"] = self.globalTransform()
        o = Vector(self.scopeState["transform"].map(Vector(0, 0, 0)))
        p = Vector(self.scopeState["transform"].map(Vector(1, 1)) - o)
        self.scopeState["centerPosition"] = o
        self.scopeState["pixelSize"] = np.abs(p)
        self.scopeState["id"] += 1  # hint to acquisition thread that state has changed

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
            self.scopeState["id"] += 1

    def _lightChanged(self):
        with self.lock:
            if self.scopeDev.lightSource is None:
                return
            self.scopeState["illumination"] = self.scopeDev.lightSource.describe()
            self.scopeState["id"] += 1

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

    def newFrame(self, data):
        self.sigNewFrame.emit(data)

    def isRunning(self):
        return self.acqThread.isRunning()

    def wait(self, *args, **kargs):
        return self.acqThread.wait(*args, **kargs)


class Frame(imaging.Frame):
    def __init__(self, data, info):
        # make frame transform to map from image coordinates to sensor coordinates.
        # (these may differ due to binning and region of interest settings)
        tr = Camera.makeFrameTransform(info["region"], info["binning"])
        info["frameTransform"] = tr

        imaging.Frame.__init__(self, data, info)


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


class MultiprocessCameraWorkers(Qt.QObject):
    """This class is used to connect the camera feed to additional processes. Requires the
    `pyacq` library to be installed. The camera should be configured with a
    'multiprocessing' parameter that specifies a list of configurations for each process
    that will receive frames from the camera. Configuration in devices.cfg looks like::

    Camera:
        ...
        multiprocessing:
            handler1:
                executable: "/optional/alternate/python/executable"
                class: "acq4.analysis.image.NoopCameraStreamHandler"
                params:
                    pollInterval: 2.0
                    onlyProcessLatestFrame: True
    """
    def __init__(self, camera: Camera, config: dict):
        super().__init__()
        try:
            import pyacq
            self._pyacq = pyacq
            HAS_PYACQ = True
        except ImportError:
            self._pyacq = None
            HAS_PYACQ = False
        self.camera = camera
        self._dtype = None
        self._shape = None
        self._config = config.get("multiprocessing", None)
        self._remote_procs = []
        self._handlers = []
        self._output = None
        self._lock = threading.Lock()
        self._isRunning = False
        self._server = None
        if HAS_PYACQ:
            if self._pyacq.RPCServer.get_server() is None:
                self._server = self._pyacq.RPCServer()
                self._server.run_lazy()  # register it in this thread
                # self._serverThread = threading.Thread(target=self._processServerRequests, daemon=True)
                # self._serverThread.start()
            self._initPyAcq(config)
        self.camera.sigNewFrame.connect(self.onNewFrame)  # this handles starting and connecting the streams

    def _processServerRequests(self):
        while True:
            self._server._read_and_process_one()
            time.sleep(0.05)

    def _initPyAcq(self, config):
        if self._config:
            self._output = self._pyacq.OutputStream()
            for name, stream_conf in self._config.items():
                remote_proc = self._pyacq.ProcessSpawner(
                    name=name, executable=stream_conf.get("executable"), qt=False)
                module = remote_proc.client._import(".".join(stream_conf.get("class").split(".")[:-1]))
                cls = getattr(module, stream_conf.get("class").split(".")[-1])
                cls_config = stream_conf.get("params", {})
                cls_config["buffer_size"] = self.bufferSize()  # enforce consistent buffer size
                handler = cls(name=name, config=cls_config)
                self._remote_procs.append(remote_proc)
                self._handlers.append(handler)

    def onNewFrame(self, frame: imaging.Frame):
        if self._output is None:
            return
        arr = frame.data()
        with self._lock:
            if arr.dtype != self._dtype or arr.shape != self._shape:
                self._dtype = arr.dtype
                self._shape = arr.shape
                self.reconfigure()
        print("Sending frame to pyacq")
        self._output.send(arr)

    def reconfigure(self):
        self.stop()
        self.start()

    def start(self):
        if self._output is None or self._isRunning:
            return
        self._output.configure(
            shape=self._shape,
            dtype=str(self._dtype),  # inifinite recursion if we don't convert to string
            axisorder=self._config.get("axisorder", None),
            double=False,  # if True, pyacq does zero-copy algorithm
            buffer_size=self.bufferSize(),
            protocol="ipc",
            transfermode="sharedmem",
            streamtype="image",
        )
        for handler in self._handlers:
            handler.connect(self._output)
        self._isRunning = True

    def bufferSize(self):
        return self._config.get("buffer_size", 30)

    def stop(self):
        if self._output is None or not self._isRunning:
            return
        self._output.close()
        for handler in self._handlers:
            handler.close()

    def quit(self):
        self.stop()
        for proc in self._remote_procs:
            proc.stop()
        if self._server is not None:
            self._server.stop()


class AcquireThread(Thread):
    sigNewFrame = Qt.Signal(object)
    sigShowMessage = Qt.Signal(object)

    def __init__(self, dev):
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

        # This thread does not run an event loop,
        # so we may need to deliver frames manually to some places
        self._newFrameCallbacks = set()
        self._newFrameCallbacksMutex = Mutex()

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
                raise Exception("Timed out waiting for camera to start.")

    def connectCallback(self, method):
        with self._newFrameCallbacksMutex:
            self._newFrameCallbacks.add(method)

    def disconnectCallback(self, method):
        with self._newFrameCallbacksMutex:
            if method in self._newFrameCallbacks:
                self._newFrameCallbacks.remove(method)

    def buildFrameInfo(self, scopeState, camState: Optional[dict] = None) -> dict:
        ps = scopeState["pixelSize"]  # size of CCD pixel
        transform = pg.SRTTransform3D(scopeState["transform"])  # TODO this is expensive; can we pull it out of the acq thread?
        if camState is None:
            info = dict(self.dev.getParams(["binning", "exposure", "region", "triggerMode"]))
        else:
            info = camState.copy()
        binning = info["binning"]
        info.update({
            "pixelSize": [ps[0] * binning[0], ps[1] * binning[1]],  # size of image pixel
            "objective": scopeState.get("objective", None),
            "deviceTransform": transform,
            "illumination": scopeState.get("illumination", None),
        })
        return info

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
            lastFrameID = None

            while True:
                now = ptime.time()
                frames = self.dev.newFrames()

                # If a new frame is available, process it and inform other threads
                if len(frames) > 0:
                    if lastFrameId is not None:
                        drop = frames[0]["id"] - lastFrameId - 1
                        if drop > 0:
                            print("WARNING: Camera dropped %d frames" % drop)

                    # Build meta-info for this frame(s)
                    info = camState.copy()

                    ss = self.dev.getScopeState()

                    if ss["id"] != lastFrameID:
                        lastFrameID = ss["id"]
                        # regenerate frameInfo here
                        frameInfo = self.buildFrameInfo(ss, camState=camState)

                    # Copy frame info to info array
                    info.update(frameInfo)  # TODO should this really be updating using last frame's info? (when ss["id"] was lastFrameID)

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
                        out = Frame(data, frameInfo)
                        with self._newFrameCallbacksMutex:
                            callbacks = list(self._newFrameCallbacks)
                        for c in callbacks:
                            c(out)
                        self.sigNewFrame.emit(out)

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
    def __init__(self, camera: Camera, frameCount: Optional[int], timeout: float = 10, ensureFreshFrames: bool = False):
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
        self._camera.acqThread.connectCallback(self.handleNewFrame)
        with ExitStack() as stack:
            if self._ensure_fresh_frames:
                stack.enter_context(self._camera.ensureRunning(ensureFreshFrames=True))
            try:
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
                        continue
                    self._frames.append(frame)
                    if self._stop_when is not None and self._stop_when(frame):
                        self._taskDone()
                        break
                    if self._frame_count is not None and len(self._frames) >= self._frame_count:
                        self._taskDone()
            finally:
                self._camera.acqThread.disconnectCallback(self.handleNewFrame)

    def handleNewFrame(self, frame):
        self._queue.put(frame)

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
