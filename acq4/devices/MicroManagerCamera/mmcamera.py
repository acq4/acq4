# -*- coding: utf-8 -*-
from __future__ import division, with_statement
import re
from collections import OrderedDict
from acq4.devices.Camera import Camera, CameraTask
from PyQt4 import QtCore
import time, sys, traceback
from numpy import *
from acq4.util.metaarray import *
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
from acq4.util.debug import *



class MicroManagerCamera(Camera):
    """Camera device that uses MicroManager to provide imaging.

    Configuration keys:

    * mmAdapterName
    * mmDeviceName
    """
    def __init__(self, manager, config, name):
        try:
            import MMCorePy
        except ImportError:
            if sys.platform != 'win32':
                raise
            # MM does not install itself to standard path. User should take care of this,
            # but we can make a guess..
            sys.path.append('C:\\Program Files\\Micro-Manager-1.4')
            try:
                import MMCorePy
            finally:
                sys.path.pop()

        self.camName = str(name)  # we will use this name as the handle to the MM camera
        self.mmc = MMCorePy.CMMCore()

        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
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
        allDevices = self.mmc.getAvailableDevices(adapterName)
        if deviceName not in allDevices:
            raise ValueError("Device name '%s' is not valid for adapter '%s'. Options are: %s" % (deviceName, adapterName, allDevices))

        self.mmc.loadDevice(self.camName, adapterName, deviceName)
        self.mmc.initializeDevice(self.camName)

        self._readAllParams()
        # import pprint
        # pprint.pprint(dict(self.listParams()))
        
    def startCamera(self):
        with self.camLock:
            self.mmc.startContinuousSequenceAcquisition(0)
            
    def stopCamera(self):
        with self.camLock:
            self.mmc.stopSequenceAcquisition()
            self.acqBuffer = None

    def _acquireFrames(self, n=1):
        self.mmc.setCameraDevice(self.camName)
        self.mmc.startSequenceAcquisition(n, 0, True)
        frames = []
        for i in range(n):
            start = time.time()
            while self.mmc.getRemainingImageCount() == 0:
                time.sleep(0.005)
                if time.time() - start > 10.0:
                    raise Exception("Timed out waiting for camera frame.")
            frames.append(self.mmc.popNextImage().T[np.newaxis, ...])
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
                frame = {}
                frame['time'] = self.lastFrameTime + (dt * (i+1))
                frame['id'] = self.frameId
                frame['data'] = self.mmc.popNextImage().T
                frames.append(frame)
                self.frameId += 1
                
        self.lastFrame = frame
        self.lastFrameTime = now
        return frames
        
    def quit(self):
        self.mmc.stopSequenceAcquisition()
        self.mmc.unloadDevice(self.camName)

    def _readAllParams(self):
        # these are parameters expected for all cameras
        defaultParams = ['exposure', 'binningX', 'binningY', 'regionX', 'regionY', 'regionW', 'regionH', 'triggerMode', 'bitDepth']

        with self.camLock:
            params = OrderedDict([(n, None) for n in defaultParams])

            properties = self.mmc.getDevicePropertyNames(self.camName)
            for prop in properties:
                vals = self.mmc.getAllowedPropertyValues(self.camName, prop)
                if vals == ():
                    if self.mmc.hasPropertyLimits(self.camName, prop):
                        vals = (
                            self.mmc.getPropertyLowerLimit(self.camName, prop),
                            self.mmc.getPropertyUpperLimit(self.camName, prop),
                        )
                else:
                    vals = list(vals)
                readonly = self.mmc.isPropertyReadOnly(self.camName, prop)
                
                # translate standard properties to the names / formats that we expect
                if prop == 'Exposure':
                    prop = 'exposure'
                    # convert ms to s
                    vals = tuple([v * 1e-3 for v in vals])
                elif prop == 'Binning':
                    vals = [v.split('x') for v in vals]
                    params['binningX'] = ([int(v[0]) for v in vals], not readonly, True, [])
                    params['binningY'] = ([int(v[1]) for v in vals], not readonly, True, [])
                    continue
                elif prop == 'Trigger':
                    prop = 'triggerMode'
                    vals = [{'NORMAL': 'Normal', 'START': 'TriggerStart'}[v] for v in vals]
                elif prop == 'PixelType':
                    prop = 'bitDepth'
                    vals = [int(bd.rstrip('bit')) for bd in vals]

                params[prop] = (vals, not readonly, True, [])

            # Reset ROI to full frame so we know the native resolution
            self.mmc.setCameraDevice(self.camName)
            self.mmc.setProperty(self.camName, 'Binning', '1x1')
            self.mmc.clearROI()
            rgn = self.mmc.getROI(self.camName)
            self._sensorSize = rgn[2:]

            params.update({
                'regionX': [(0, rgn[2]-1, 1), True, True, []],
                'regionY': [(0, rgn[3]-1, 1), True, True, []],
                'regionW': [(1, rgn[2], 1), True, True, []],
                'regionH': [(1, rgn[3], 1), True, True, []],
            })

        self._allParams = params

    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        if params is None:
            return self._allParams.copy()
        if isinstance(params, basestring):
            return self._allParams[params]
        return dict([(p, self._allParams[p]) for p in params])

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        # umanager will refuse to set params while camera is running,
        # so autoRestart doesn't make sense in this context
        if self.isRunning():
            restart = True
            self.stop()
        else:
            restart = False

        newVals = {}
        for k,v in params.items():
            self._setParam(k, v, autoCorrect=autoCorrect)
            if k == 'binning':
                newVals['binningX'], newVals['binningY'] = self.getParam(k)
            elif k == 'region':
                newVals['regionX'], newVals['regionY'], newVals['regionW'], newVals['regionH'] = self.getParam(k)
            else:
                newVals[k] = self.getParam(k)
        self.sigParamsChanged.emit(newVals)

        if restart:
            self.start()

        needRestart = False
        return (newVals, needRestart)

    def setParam(self, param, value, autoCorrect=True, autoRestart=True):
        return self.setParams({param: value}, autoCorrect=autoCorrect, autoRestart=autoRestart)

    def _setParam(self, param, value, autoCorrect=True):
        if param == 'region':
            value = (value[0], value[1], value[2], value[3])
            self.mmc.setCameraDevice(self.camName)
            self.mmc.setROI(*value)
            return

        if param.startswith('region'):
            rgn = list(self.mmc.getROI(self.camName))
            if param[-1] == 'X':
                rgn[0] = value
            elif param[-1] == 'Y':
                rgn[1] = value
            elif param[-1] == 'W':
                rgn[2] = value
            elif param[-1] == 'H':
                rgn[3] = value
            self.mmc.setCameraDevice(self.camName)
            self.mmc.setROI(*rgn)
            return

        if param.startswith('binning'):
            if param == 'binningX':
                y = self.getParam('binningY')
                value = (value, y)
                param = 'binning'
            elif param == 'binningY':
                x = self.getParam('binningX')
                value = (x, value)
                param = 'binning'
            value = '%dx%d' % value
            param = 'Binning'

        elif param == 'exposure':
            # s to ms
            value = value * 1e3
            param = 'Exposure'

        elif param == 'triggerMode':
            value = {'Normal': 'NORMAL', 'TriggerStart': 'START'}[value]
            param = 'Trigger'

        with self.camLock:
            self.mmc.setProperty(self.camName, str(param), str(value))

    def getParams(self, params=None):
        if params is None:
            params = self.listParams().keys()
        return dict([(p, self.getParam(p)) for p in params])

    def getParam(self, param):
        if param == 'sensorSize':
            return self._sensorSize
        elif param.startswith('region'):
            rgn = self.mmc.getROI(self.camName)
            if param == 'region':
                return rgn
            i = ['regionX', 'regionY', 'regionW', 'regionH'].index(param)
            return rgn[i]

        paramTrans = {
            'exposure': 'Exposure',
            'binning': 'Binning',
            'binningX': 'Binning',
            'binningY': 'Binning',
            'triggerMode': 'Trigger',
            'bitDepth': 'PixelType',
        }.get(param, param)
        with self.camLock:
            val = self.mmc.getProperty(self.camName, str(paramTrans))

        # coerce to int or float if possible
        try:
            val = int(val)
        except ValueError:
            try:
                val = float(val)
            except ValueError:
                pass

        if param == 'binningY':
            return int(val.split('x')[1])
        elif param == 'binningX':
            return int(val.split('x')[0])
        elif param == 'binning':
            return tuple([int(b) for b in val.split('x')])
        elif param == 'exposure':
            # ms to s
            val = val * 1e-3
        elif param == 'bitDepth':
            return int(val.rstrip('bit'))

        return val

