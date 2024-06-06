import time
from collections import OrderedDict
from functools import lru_cache

import numpy as np

import acq4.util.ptime as ptime
from acq4.devices.Camera import Camera
from acq4.util import micromanager
from acq4.util.Mutex import RecursiveMutex
from acq4.util.debug import printExc
from acq4.util.micromanager import MicroManagerError
from pyqtgraph.debug import Profiler

# Micromanager does not standardize trigger modes across cameras,
# so we use this dict to translate the modes of various cameras back
# to the standard ACQ4 modes:
#   Normal: Camera starts by software and acquires frames on its own clock
#   TriggerStart: Camera starts by trigger and acquires frames on its own clock
#   Strobe: Camera acquires one frame of a predefined exposure time for every trigger pulse
#   Bulb: Camera exposes one frame for the duration of each trigger pulse

triggerModes = {
    'TriggerType': {'Freerun': 'Normal'},  # QImaging 
    'Trigger': {'NORMAL': 'Normal', 'START': 'TriggerStart'},  # Hamamatsu
}


class MicroManagerCamera(Camera):
    """Camera device that uses MicroManager to provide imaging.

    Requires pymmcore to be installed along with MicroManager with the same API version.
    To configure a new camera:
    1. First make sure your pymmcore API version matches the MicroManager API version.
        - MicroManager API version can be found in the MicroManager GUI under Help -> About.
        - pymmcore API version can be found by running `import pymmcore; print(pymmcore.__version__.split('.')[3])`
        - If versions are not matched, then download a different version of MicroManager that matches the pymmcore version.
    2. Next make sure you can load and operate the camera via the MicroManager GUI. 
        - When selecting your camera in the hardware wizard, take note of the adapter name and device name
    3. Configure the camera in the ACQ4 configuration file::

        Camera:
            driver: 'MicroManagerCamera'
            mmAdapterName: 'HamamatsuHam'
            mmDeviceName: 'HamamatsuHam_DCAM'
    """

    def __init__(self, manager, config, name):
        self.camName = str(name)  # we will use this name as the handle to the MM camera
        mmpath = config.get('path')
        self.mmc = micromanager.getMMCorePy(mmpath)

        self._triggerProp = None  # the name of the property for setting trigger mode
        self._triggerModes = ({}, {})  # forward and reverse mappings for the names of trigger modes
        self._binningMode = None  # 'x' or 'xy' for binning strings like '1' and '1x1', respectively
        self.camLock = RecursiveMutex()  ## Lock to protect access to camera
        self._config = config
        Camera.__init__(self, manager, config, name)  ## superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastFrameTime = None

    def setupCamera(self):
        # sanity check for MM adapter and device name
        adapterName = self._config['mmAdapterName']
        allAdapters = self.mmc.getDeviceAdapterNames()
        if adapterName not in allAdapters:
            raise ValueError("Adapter name '%s' is not valid. Options are: %s" % (adapterName, allAdapters))
        deviceName = self._config['mmDeviceName']
        try:
            allDevices = self.mmc.getAvailableDevices(adapterName)
        except Exception as e:
            raise RuntimeError(f"Error getting available devices for MicroManager adapter '{adapterName}'. {micromanager.versionWarning()}") from e
        if deviceName not in allDevices:
            raise ValueError("Device name '%s' is not valid for adapter '%s'. Options are: %s" % (
                deviceName, adapterName, allDevices))
        if deviceName == 'CellCam':
            self.camName = 'CellCam' # load.Device() for CellCam needs to have 'CellCam' as device name
        self.mmc.loadDevice(self.camName, adapterName, deviceName)
        
        # the 'Camera ID' property is not prefilled after loadDevice(). Need to assign it:
        if self.camName == 'CellCam':
            self.mmc.setProperty(self.camName, 'Camera ID', ''.join(self.mmc.getAllowedPropertyValues('CellCam', 'Camera ID'))) 
        self.mmc.initializeDevice(self.camName)

        self._readAllParams()

    def startCamera(self):
        with self.camLock:
            self.mmc.startContinuousSequenceAcquisition(0)

    def stopCamera(self):
        with self.camLock:
            self.mmc.stopSequenceAcquisition()
            self.acqBuffer = None

    def isRunning(self):
        # This is needed to allow calling setParam inside startCamera before the acquisition has actually begun
        # (but after the acquisition thread has started)
        return self.mmc.isSequenceRunning()

    def _acquireFrames(self, n=1):
        if self.isRunning():
            self.stop()
        with self.camLock:
            self.mmc.setCameraDevice(self.camName)
            self.mmc.startSequenceAcquisition(n, 0, True)
            frames = []
            timeoutStart = ptime.time()
            while self.mmc.isSequenceRunning() or self.mmc.getRemainingImageCount() > 0:
                if self.mmc.getRemainingImageCount() > 0:
                    timeoutStart = ptime.time()
                    frames.append(self.mmc.popNextImage().T[np.newaxis, ...])
                elif ptime.time() - timeoutStart > 10.0:
                    raise TimeoutError("Timed out waiting for camera frame.")
                else:
                    time.sleep(0.005)
        if len(frames) < n:
            printExc(
                f"Fixed-frame camera acquisition ended before all frames received ({len(frames)}/{n})",
                msgType="warning"
            )
        self.mmc.stopSequenceAcquisition()
        return np.concatenate(frames, axis=0)

    def newFrames(self):
        """Return a list of all frames acquired since the last call to newFrames."""

        with self.camLock:
            nFrames = self.mmc.getRemainingImageCount()
            if nFrames == 0:
                return []

        now = ptime.time()
        if self.lastFrameTime is None:
            self.lastFrameTime = now

        dt = (now - self.lastFrameTime) / nFrames
        frames = []
        with self.camLock:
            for i in range(nFrames):
                frames.append({
                    'time': self.lastFrameTime + (dt * (i + 1)),
                    'id': self.frameId,
                    'data': self.mmc.popNextImage().T,
                })
                self.frameId += 1

        self.lastFrame = frames[-1]
        self.lastFrameTime = now
        return frames

    def quit(self):
        self.mmc.stopSequenceAcquisition()
        self.mmc.unloadDevice(self.camName)

    def _readAllParams(self):
        # these are parameters expected for all cameras
        defaultParams = ['exposure', 'binningX', 'binningY', 'regionX', 'regionY', 'regionW', 'regionH', 'triggerMode']

        with self.camLock:
            params = OrderedDict([(n, None) for n in defaultParams])

            properties = self.mmc.getDevicePropertyNames(self.camName) + ('Exposure',) # because the CellCam driver didn't present the exposure as a property, need to add it with a getExposure() call
            for prop in properties:
                vals = self.mmc.getAllowedPropertyValues(self.camName, prop)
                if vals == ():
                    if self.camName == 'CellCam' and prop == 'Exposure':
                        vals = (1, 100) # sensible range of exposure values...
                    elif self.mmc.hasPropertyLimits(self.camName, prop):
                        vals = (
                            self.mmc.getPropertyLowerLimit(self.camName, prop),
                            self.mmc.getPropertyUpperLimit(self.camName, prop),
                        )
                    else:
                        # just guess..
                        vals = (1e-6, 1e3)
                vals = list(vals)
                if self.camName == 'CellCam' and prop == 'Exposure':
                    readonly = False  # again, workaround...
                else:
                    readonly = self.mmc.isPropertyReadOnly(self.camName, prop)

                # translate standard properties to the names / formats that we expect
                if prop == 'Exposure':
                    prop = 'exposure'
                    # convert ms to s
                    vals = tuple([v * 1e-3 for v in vals])
                elif prop == 'Binning':
                    for i in range(len(vals)):
                        if 'x' in vals[i]:
                            vals[i] = vals[i].split('x')
                            self._binningMode = 'xy'
                        else:
                            vals[i] = [vals[i], vals[i]]
                            self._binningMode = 'x'
                    params['binningX'] = ([int(v[0]) for v in vals], not readonly, True, [])
                    params['binningY'] = ([int(v[1]) for v in vals], not readonly, True, [])
                    continue
                elif prop in triggerModes:
                    self._triggerProp = prop
                    modes = triggerModes[prop]
                    self._triggerModes = (modes, {v: k for k, v in modes.items()})
                    prop = 'triggerMode'
                    vals = [modes[v] for v in vals]

                # translation from PixelType to bitDepth is not exact; this will take more work.
                # for now we just expose PixelType directly.
                # elif prop == 'PixelType':
                #     prop = 'bitDepth'
                #     vals = [int(bd.rstrip('bit')) for bd in vals]

                params[prop] = (vals, not readonly, True, [])

            # Reset ROI to full frame so we know the native resolution
            self.mmc.setCameraDevice(self.camName)
            bin = '1' if self._binningMode == 'x' else '1x1'
            self.mmc.setProperty(self.camName, 'Binning', bin)
            self.mmc.clearROI()
            rgn = self.getROI()
            self._sensorSize = rgn[2:]

            params.update({
                'regionX': [(0, rgn[2] - 1, 1), True, True, []],
                'regionY': [(0, rgn[3] - 1, 1), True, True, []],
                'regionW': [(1, rgn[2], 1), True, True, []],
                'regionH': [(1, rgn[3], 1), True, True, []],
            })

            if params['triggerMode'] is None:
                params['triggerMode'] = (['Normal'], False, True, [])

            if params['binningX'] is None:
                params['binningX'] = [[1], False, True, []]
                params['binningY'] = [[1], False, True, []]

            self._allParams = params

    def getROI(self):
        camRegion = self.mmc.getROI(self.camName)
        if self._useBinnedPixelsForROI:
            xAdjustment = self.getParam("binningX")
            yAdjustment = self.getParam("binningY")
        else:
            xAdjustment = 1
            yAdjustment = 1
        return [
            camRegion[0] * xAdjustment,
            camRegion[1] * yAdjustment,
            camRegion[2] * xAdjustment,
            camRegion[3] * yAdjustment,
        ]

    def setROI(self, rgn):
        if self._useBinnedPixelsForROI:
            rgn[0] = int(rgn[0] / self.getParam('binningX'))
            rgn[1] = int(rgn[1] / self.getParam('binningY'))
            rgn[2] = int(rgn[2] / self.getParam('binningX'))
            rgn[3] = int(rgn[3] / self.getParam('binningY'))
        self.mmc.setROI(*rgn)

    @lru_cache(maxsize=None)
    def _useBinnedPixelsForROI(self):
        # Adjusting ROI to be in binned-pixel units is necessary in all versions of
        # MMCore 7.0.2 and above.
        version = self.mmc.getVersionInfo()  # e.g. "MMCore version 7.0.2"
        ver_num = version.split(" ")[-1].split(".")
        ver_tup = tuple([int(d) for d in ver_num])
        return ver_tup >= (7, 0, 2)

    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        if params is None:
            return self._allParams.copy()
        if isinstance(params, str):
            return self._allParams[params]
        return dict([(p, self._allParams[p]) for p in params])

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        p = Profiler(disabled=True, delayed=False)

        # umanager will refuse to set params while camera is running,
        # so autoRestart doesn't make sense in this context
        if self.isRunning():
            restart = autoRestart
            self.stop()
            p('stop')
        else:
            restart = False

        # Join region params into one request (_setParam can be very slow)
        regionKeys = ['regionX', 'regionY', 'regionW', 'regionH']
        nRegionKeys = len([k for k in regionKeys if k in params])
        if nRegionKeys > 1:
            rgn = list(self.getROI())
            for k in regionKeys:
                if k not in params:
                    continue
                i = {'X': 0, 'Y': 1, 'W': 2, 'H': 3}[k[-1]]
                rgn[i] = params[k]
                del params[k]
            params['region'] = rgn

        newVals = {}
        for k, v in params.items():
            try:
                self._setParam(k, v, autoCorrect=autoCorrect)
            except MicroManagerError as e:
                printExc(f"Unable to set {k} param to {v}: {e}")
            else:
                p(f'setParam {k!r}')
                if k == 'binning':
                    newVals['binningX'], newVals['binningY'] = self.getParam(k)
                elif k == 'region':
                    newVals['regionX'], newVals['regionY'], newVals['regionW'], newVals['regionH'] = self.getParam(k)
                else:
                    newVals[k] = self.getParam(k)
                p('reget param')
        self.sigParamsChanged.emit(newVals)
        p('emit')

        if restart:
            self.start()
            p('start')

        needRestart = False
        return newVals, needRestart

    def setParam(self, param, value, autoCorrect=True, autoRestart=True):
        return self.setParams({param: value}, autoCorrect=autoCorrect, autoRestart=autoRestart)

    def _setParam(self, param, value, autoCorrect=True):
        if param.startswith('region'):
            if param == 'region':
                rgn = [value[0], value[1], value[2], value[3]]
            else:
                rgn = list(self.getROI())
                if param[-1] == 'X':
                    rgn[0] = value
                elif param[-1] == 'Y':
                    rgn[1] = value
                elif param[-1] == 'W':
                    rgn[2] = value
                elif param[-1] == 'H':
                    rgn[3] = value
            self.mmc.setCameraDevice(self.camName)
            self.setROI(rgn)
            return

        # translate requested parameter into a list of sub-parameters to set
        setParams = []

        if param.startswith('binning'):
            if self._binningMode is None:
                # camera does not support binning; only allow values of 1
                if value in [1, (1, 1)]:
                    return
                else:
                    raise ValueError('Invalid binning value %s=%s' % (param, value))

            if param == 'binningX':
                y = self.getParam('binningY')
                value = (value, y)
            elif param == 'binningY':
                x = self.getParam('binningX')
                value = (x, value)

            if self._binningMode == 'x':
                value = '%d' % value[0]
            else:
                value = '%dx%d' % value

            setParams.append(('Binning', value))

        elif param == 'exposure':
            # s to ms
            setParams.append(('Exposure', value * 1e3))

        elif param == 'triggerMode':
            if self._triggerProp is None:
                # camera does not support triggering; only allow 'Normal' mode
                if value != 'Normal':
                    raise ValueError("Invalid trigger mode '%s'" % value)
                return

            # translate trigger mode name
            setParams.append((self._triggerProp, self._triggerModes[1][value]))

            # Hamamatsu cameras require setting a trigger source as well
            if self._config['mmAdapterName'] == 'HamamatsuHam':
                if value == 'Normal':
                    source = 'INTERNAL'
                elif value == 'TriggerStart':
                    source = 'EXTERNAL'
                else:
                    raise ValueError("Invalid trigger mode '%s'" % value)
                # On Orca 4 we actually have to toggle the source property
                # back and forth, otherwise it is sometimes ignored.
                setParams.append(('TRIGGER SOURCE', 'INTERNAL'))
                setParams.append(('TRIGGER SOURCE', source))

        else:
            setParams.append((param, value))

        # elif param == 'bitDepth':
        #     param = 'PixelType'
        #     value = '%dbit' % value

        with self.camLock:
            for param, value in setParams:
                if param == 'Exposure' and self.camName == "CellCam":
                    # workaround for CellCam - call to setExposure(), not getProperty()
                    self.mmc.setExposure(self.camName, value)
                else:
                    self.mmc.setProperty(self.camName, str(param), str(value))

    def getParams(self, params=None):
        if params is None:
            params = list(self.listParams().keys())
        return dict([(p, self.getParam(p)) for p in params])

    def getParam(self, param):
        if param == 'sensorSize':
            return self._sensorSize
        elif param.startswith('region'):
            rgn = self.getROI()
            if param == 'region':
                return rgn
            i = ['regionX', 'regionY', 'regionW', 'regionH'].index(param)
            return rgn[i]
        elif param.startswith('binning') and self._binningMode is None:
            # camera does not support binning; fake it here
            if param == 'binning':
                return 1, 1
            elif param in ('binningX', 'binningY'):
                return 1
        elif param == 'triggerMode' and self._triggerProp is None:
            # camera does not support triggering; fake it here
            return 'Normal'

        paramTrans = {
            'exposure': 'Exposure',
            'binning': 'Binning',
            'binningX': 'Binning',
            'binningY': 'Binning',
            'triggerMode': self._triggerProp,
            'bitDepth': 'PixelType',
        }.get(param, param)
        with self.camLock:
            if paramTrans == 'Exposure' and self.camName == "CellCam":
                val = self.mmc.getExposure(self.camName) # workaround for CellCam
            else:
                val = self.mmc.getProperty(self.camName, str(paramTrans))

        # coerce to int or float if possible
        try:
            val = int(val)
        except ValueError:
            try:
                val = float(val)
            except ValueError:
                pass

        if param in ('binning', 'binningX', 'binningY'):
            if self._binningMode == 'x':
                val = (int(val),) * 2
            else:
                val = tuple([int(b) for b in val.split('x')])

            if param == 'binningY':
                return val[1]
            elif param == 'binningX':
                return val[0]
            elif param == 'binning':
                return val
        elif param == 'exposure':
            # ms to s
            val = val * 1e-3
        # elif param == 'bitDepth':
        #     val = int(val.rstrip('bit'))
        elif param == 'triggerMode':
            val = self._triggerModes[0][val]

        return val
