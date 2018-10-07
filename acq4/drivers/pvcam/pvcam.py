# -*- coding: utf-8 -*-
from __future__ import print_function

import six

from ctypes import *
import sys, numpy, time, re, os, platform
from acq4.util.clibrary import *
from collections import OrderedDict
from acq4.util.debug import backtrace
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
import atexit

__all__ = ['PVCam']


### Load header files, open DLL
modDir = os.path.dirname(__file__)
headerFiles = [
    #"C:\Program Files\Photometrics\PVCam32\SDK\inc\master.h",
    #"C:\Program Files\Photometrics\PVCam32\SDK\inc\pvcam.h"
    os.path.join(modDir, "master.h"),
    os.path.join(modDir, "pvcam.h")
]
HEADERS = CParser(headerFiles, cache=os.path.join(modDir, 'pvcam_headers.cache'), copyFrom=winDefs())

if platform.architecture()[0] == '64bit':
    LIB = CLibrary(windll.Pvcam64, HEADERS, prefix='pl_')
else:
    LIB = CLibrary(windll.Pvcam32, HEADERS, prefix='pl_')


### Default configuration parameters. 
### All cameras use the parameters under 'ALL'
### If a camera model matches another key, then those values override.
### format for each camera is [ (paramName, value, range, writable, readable, deps), ... ]

###   - PARAM_BIT_DEPTH, PARAM_PIX_TIME, and PARAM_GAIN_INDEX(ATTR_MAX)
###     are determined by setting PARAM_READOUT_PORT and PARAM_SPDTAB_INDEX 
###   - PARAM_GAIN_INDEX must be set AFTER setting PARAM_SPDTAB_INDEX


cameraDefaults = {
    'ALL': [
        #('PMODE', LIB.PMODE_NORMAL),  ## PMODE_FT ?
        ('SHTR_OPEN_MODE', LIB.OPEN_PRE_SEQUENCE),
        ('CLEAR_MODE', LIB.CLEAR_PRE_EXPOSURE),
        ('CLEAR_CYCLES', 2),
    ],
        
    'QUANTEM:512SC': [
        ('READOUT_PORT', 0),  ## fastest for QuantEM
        ('SPDTAB_INDEX', 0),  ## Fastest option for QM512
        ('CLEAR_MODE', LIB.CLEAR_PRE_SEQUENCE),  ## Overlapping mode for QuantEM cameras
        ('GAIN_INDEX', 2),
        ('binningX', 1, range(1,9)),
        ('binningY', 1, range(1,9)),
    ],
    
    'Quantix57': [
        ('READOUT_PORT', 0),  ## Only option for Q57
        ('SPDTAB_INDEX', 2),  ## Fastest option for Q57
        ('binningX', 1, [1,2,3,4,8,12,16,24,32,48,64,128,256,512]),
        ('binningY', 1, [1,2,3,4,8,12,16,24,32,48,64,128,256,512]),
    ],
}
cameraDefaults['Quantix EEV57  '] = cameraDefaults['Quantix57']  ## different names, same camera.



### List of parameters we want exposed to the outside
### (We could just list all parameters from the DLL, but it turns out there are many that we do not 
### want to expose)
externalParams = [
    'READOUT_PORT',
    'SPDTAB_INDEX',
    'BIT_DEPTH',
    'PIX_TIME',
    'GAIN_INDEX',
    'GAIN_MULT_ENABLE',
    'GAIN_MULT_FACTOR',
    'INTENSIFIER_GAIN',
    #'EXPOSURE_MODE',
    'PREFLASH',
    'CLEAR_MODE',
    'CLEAR_CYCLES',
    'SHTR_OPEN_MODE',
    'SHTR_OPEN_DELAY',
    'ANTI_BLOOMING',
    'TEMP_SETPOINT',
    'COOLING_MODE',    
    'TEMP',
    'PIX_SER_SIZE',
    'PIX_PAR_SIZE',
]





def init():
    ## System-specific code
    global PVCam
    PVCam = _PVCamClass()


class _PVCamClass:
    """This class is an interface to the PVCam driver; NOT an interface to any particular camera."""
    PVCAM_CREATED = False
    
    def __init__(self):
        self.cams = {}
        self.lock = Mutex()

        #self.pvcam = windll.Pvcam32
        if _PVCamClass.PVCAM_CREATED:
            raise Exception("Will not create another pvcam instance--use the pre-existing PVCam object.")
        init = LIB.pvcam_init()()
        if init < 1:
            raise Exception("Could not initialize pvcam library (pl_pvcam_init): %s" % self.error())
        # This should happen before every new exposure (?)
        if LIB.exp_init_seq()() < 1:
            raise Exception("Could not initialize pvcam library (pl_exp_init_seq): %s" % self.error())
        _PVCamClass.PVCAM_CREATED = True
        
        
        global externalParams
        
        self.paramTable = OrderedDict()
        for p in externalParams:
            self.paramTable[p] = self.paramFromString(p)

        atexit.register(self.quit)

    def reloadDriver(self):
        #if self.pvcam.pl_pvcam_uninit() < 1:
            #raise Exception("Could not un-initialize pvcam library (pl_pvcam_init): %s" % self.error())
        #self.pvcam = windll.Pvcam32
        #if self.pvcam.pl_pvcam_init() < 1:
            #raise Exception("Could not initialize pvcam library (pl_pvcam_init): %s" % self.error())
        self.quit()
        self.__init__()

    def listCameras(self):
        #nCam = c_int()
        cams = []
        nCams = LIB.cam_get_total()[0]
        if nCams < 1:
            err = self.errno()
            if err == 0:
                return []
            else:
                raise Exception("Error getting number of cameras: %s" % self.error(err))
        for i in range(nCams):
            cName = create_string_buffer(b'\0' * LIB.CAM_NAME_LEN)
            if LIB.cam_get_name(i, cName)() < 1:
                raise Exception("Error getting name for camera %d: %s" % (i, self.error()))
            cams.append(cName.value)
        return cams

    def getCamera(self, cam):
        if cam not in self.cams:
            self.cams[cam] = _CameraClass(cam, self)
        return self.cams[cam]
    
    def call(self, func, *args, **kargs):
        with self.lock:
            # print ">>", func, args, kargs
            fn = LIB('functions', func)
            res = fn(*args, **kargs)
            if res() < 1:
                raise Exception("Function '%s%s' failed: %s" % (func, str(args), self.error()), self.errno())
            # print "<<", func
            return res

    def errno(self):
        erc = LIB.error_code()()
        return erc

    def error(self, erno=None):
        if erno is None:
            erno = LIB.error_code()()
        err = create_string_buffer(b'\0'*LIB.ERROR_MSG_LEN)
        LIB.error_message(erno, err)
        return "%d: %s" % (erno, err.value)

    def quit(self):
        for c in self.cams:
            try:
                self.cams[c].close()
            except:
                pass
        if not hasattr(self, 'pvcam'):
            return
        self.call('exp_uninit_seq')
        self.call('pvcam_uninit')
        _PVCamClass.PVCAM_CREATED = False

    def listParams(self, allParams=False):
        #return [x[6:] for x in self.defs if x[:6] == 'PARAM_']
        if allParams:
            return [p[2][6:] for p in HEADERS.find(re.compile('PARAM_.*'))]
        else:
            return list(self.paramTable.keys())
    
    def paramFromString(self, p):
        """Return the driver's param ID for the given parameter name."""
        
        if isinstance(p, six.string_types):
            if p == 'bitDepth':
                p = 'BIT_DEPTH'
            try:
                return LIB('values', 'PARAM_' + p)
            except NameError:
                raise Exception("No parameter named '%s'" % p)
        else:
            return p
            
    def paramToString(self, p):
        """Return the parameter name given the driver's param ID."""
        ps = self.paramTable[p]
        if ps == 'BIT_DEPTH':
            ps = 'bitDepth'
        return ps
        

class _CameraClass:
    def __init__(self, name, pvcam):
        self.name = name
        self.pvcam = pvcam
        self.isOpen = False
        self.open()
        
        self.mode = 0
        self.buf = None
        
        ## Some parameters, when set, may cause other parameters to change as well:
        self.paramValueDeps = {
            'READOUT_PORT': ['SPDTAB_INDEX', 'BIT_DEPTH', 'PIX_TIME', 'GAIN_INDEX'], 
            'SPDTAB_INDEX': ['BIT_DEPTH', 'PIX_TIME', 'GAIN_INDEX'],
        }
        
        self.enumTable = self._buildEnumTable()  ## stores bi-directional hashes of enum strings and values
        
        ## Some parameters are just locally stored variables, all the rest actually reside on the camera
        self.localParamNames = ['triggerMode', 'exposure', 'binningX', 'binningY', 'regionX', 'regionY', 'regionW', 'regionH', 'ringSize']

        ## Some parameters can be accessed as groups
        self.groupParams = {
            'binning': ['binningX', 'binningY'],
            'region': ['regionX', 'regionY', 'regionW', 'regionH'],
            'sensorSize': ['SER_SIZE', 'PAR_SIZE'] 
        }


        self.paramValues = {}  ## storage for local params and cache for remote params
                               ## remote params must be cached because reading them can cause
                               ## the camera to stop.
        
        self.paramAttrs = OrderedDict()   ## dict of all parameters available to the user and ranges, read/write, dependencies.
                                          ## Note this dict is ordered so we can display params to the user in a logical fashion 
        for p in self.localParamNames:
            ## get these in the list now so they show up first
            self.paramAttrs[p] = None
        
        self.paramAttrs.update(self._buildParamList())  ## list of acceptable values for each parameter
        
        ## correct the stupid
        #if 'GAIN_INDEX' in self.paramAttrs:
        try:
            self.paramAttrs['GAIN_INDEX'][0] = self.paramAttrs['GAIN_INDEX'][0][:2] + (1,)    ## why did they set the step value to 0? Who knows?
        except KeyError:
            print(self.paramAttrs)
            raise Exception("'GAIN_INDEX' missing from camera parameters. Try restarting your camera.")
        
        ## define standard dependencies
        #if 'READOUT_PORT' in self.paramAttrs:
        self.paramAttrs['READOUT_PORT'][3] = ['SPDTAB_INDEX', 'GAIN_INDEX']
        #if 'SPDTAB_INDEX' in self.paramAttrs:
        self.paramAttrs['SPDTAB_INDEX'][3] = ['GAIN_INDEX']
        
        
        size = self.getParam('sensorSize')
        self.paramValues = {  ## list of current values for parameters not handled by driver
            'binningX': 1,
            'binningY': 1,
            'exposure': 0.001,
            'triggerMode': 'Normal',
            'regionX': 0,
            'regionY': 0,
            'regionW': size[0],
            'regionH': size[1],
            'ringSize': 10,
        }        
        
        self.paramAttrs.update({
            #'binningX': [(1, size[0], 1), True, True, []],  
            #'binningY': [(1, size[1], 1), True, True, []],
            'binningX': [[1,2,4,8,16], True, True, []],    ## Just a guess.. this should be overwritten once we know what the camera model is.
            'binningY': [[1,2,4,8,16], True, True, []],
            'exposure': [(0, None, None), True, True, []],
            'triggerMode': [['Normal', 'TriggerStart', 'Strobe', 'Bulb'], True, True, []],
            'regionX': [(0, size[0]-1, 1), True, True, []],
            'regionY': [(0, size[1]-1, 1), True, True, []],
            'regionW': [(1, size[0], 1), True, True, []],
            'regionH': [(1, size[1], 1), True, True, []],
            'ringSize': [(2, None, 1), True, True, []],
        })
        
        ## Generate list of all remote parameter names
        self.remoteParamNames = list(self.paramAttrs.keys())
        for k in self.localParamNames:
            self.remoteParamNames.remove(k)
        
        ## Read and cache all parameter values
        self.paramValues.update(self.getParams(self.remoteParamNames))
        
        ## Determine camera type; load default settings
        self.initCam()

    def __del__(self):
        self.close()

    def open(self):
        ## Driver bug; try opening twice.
        try:
            self.hCam = self.call('cam_open', self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
            #self.hCam = LIB.cam_open(self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
        except:
            self.hCam = self.call('cam_open', self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
            #self.hCam = LIB.cam_open(self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
        self.isOpen = True

    def close(self):
        if self.isOpen:
            #self.pvcam.pl_exp_abort(CCS_HALT_CLOSE_SHUTTER)
            self.call('cam_close', self.hCam)
            self.isOpen = False
            
    def call(self, fn, *args, **kargs):
        # ret = LIB('functions', fn)(*args, **kargs)
        # return ret
        return self.pvcam.call(fn, *args, **kargs)

    def initCam(self, params=None):
        buf = create_string_buffer(b'\0' * LIB.CCD_NAME_LEN)
        camType = self.call('get_param', self.hCam, LIB.PARAM_CHIP_NAME, LIB.ATTR_CURRENT, buf)[3]
        
        ## Implement default settings for this camera model
        defaults = OrderedDict([(p[0], p[1]) for p in cameraDefaults['ALL']])
        ranges = dict([(p[0], p[2:]) for p in cameraDefaults['ALL']])
        
        
        if camType in cameraDefaults:
            print("Loading default settings for", camType)
            camDefaults = OrderedDict([(p[0], p[1]) for p in cameraDefaults[camType]])
            camRanges = dict([(p[0], p[2:]) for p in cameraDefaults[camType]])
            defaults.update(camDefaults)
            ranges.update(camRanges)
        else:
            print("Warning--camera model '%s' is unrecognized; default settings may be incorrect." % camType)
        
        for k,v in ranges.items():
            #print self.paramAttrs[k], k, v
            for i in range(len(v)):
                self.paramAttrs[k][i] = v[i]
        
        self.setParams(defaults)
        

    def listParams(self, params=None):
        """Return the dict of all parameters with bounds, read/write access, and dependencies"""
        
        if params is None:
            return self.paramAttrs.copy()
        else:
            unList = False
            if isinstance(params, six.string_types):
                params = [params]
                unList = True
                #try:
                    #return self.paramAttrs[params]
                #except KeyError:
                    #print self.paramAttrs.keys()
                    #raise Exception("No parameter named '%s'. Full list is printed above." % params)
                
            plist = params
            params = {}
            for p in plist:
                try:
                    params[p] = self.paramAttrs[p]
                except KeyError:
                    #print self.paramAttrs.keys()
                    raise Exception("No parameter named '%s'. Params are:" % (p, str(list(self.paramAttrs.keys()))))
                
            if unList:
                return params[plist[0]]
            return params


            
    def getParams(self, params, asList=False):
        """Get a list of parameter values. Return a dictionary of name: value pairs"""
        if asList:
            return [self.getParam(p) for p in params]
        else:
            return OrderedDict([(p, self.getParam(p)) for p in params])

    def getParam(self, param):
        """Get the value of a single parameter."""
        #print "GetParam:", param
        
        if param in self.groupParams:
            return self.getParams(self.groupParams[param], asList=True)
        
        if param not in self.paramValues:
            paramId = self.pvcam.paramFromString(param)
            self._assertParamReadable(paramId)
            self.paramValues[param] = self._getParam(paramId, LIB.ATTR_CURRENT)
        return self.paramValues[param]
        
    def setParams(self, params, autoCorrect=True, forceSet=False):
        """Set the values of multiple parameters. Format may be {name: value, ...} or [(name, value), ...]"""
        newVals = OrderedDict()
        if isinstance(params, dict):
            plist = list(params.items())
        else:
            plist = params
            
        restart = []
        for p, v in plist:
            (changes, res) = self.setParam(p, v, autoCorrect=autoCorrect, forceSet=forceSet)
            newVals.update(changes)
            restart.append(res)
        return (newVals, any(restart))
        
    def setParam(self, paramName, value, autoCorrect=True, forceSet=False):
        """Set a single parameter. This can be a local or camera parameter, and can also be a grouped parameter.
        Returns a tuple of the value set and a boolean indicating whether the camera must be reset to activate the
        new settings.
        
        If autoCorrect is True, then value is adjusted to fit in bounds and quantized, and the new value is returned.
        Normally, camera parameters that do not need to be set (because they are already) will be ignored. However, this can be
        overridden with forceSet."""
        if paramName in self.groupParams:
            return self.setParams(list(zip(self.groupParams[paramName], value)))
        
        ## If this is an enum parameter, convert string values to int before setting
        if paramName in self.enumTable:
            if isinstance(value, six.string_types):
                strVal = value
                value = self.enumTable[paramName][0][value]
            else:
                strVal = self.enumTable[paramName][1][value]
        
        ## see if we can ignore parameter set because it is already set
        if not forceSet:
            currentVal = self.getParam(paramName)
                
            if (currentVal == value):
                #print "not setting parameter %s; unchanged" % paramName
                return ({paramName:value}, False)
            elif  (paramName in self.enumTable) and (currentVal == strVal):
                #print "not setting parameter %s; unchanged" % paramName
                return ({paramName:strVal}, False)
            #else:
                #print "will set parameter %s: new %s != old %s" % (paramName, str(value), str(currentVal))
        
        if paramName in self.localParamNames:
            return self._setLocalParam(paramName, value, autoCorrect)
        
        param = self.pvcam.paramFromString(paramName)
        self._assertParamReadable(param)

        if isinstance(value, six.string_types):
            try:
                value = getattr(LIB, value)
            except:
                raise Exception("Unrecognized value '%s'. Options are: %s" % (value, str(list(self.pvcam.defs.keys()))))

        
        #print "   PVCam setParam lookup param"
        #param = self.pvcam.param(param)
        self._assertParamWritable(param)
        #print "   PVCam setParam param writable"

        ## Determine the parameter type
        typ = self.getParamType(param)
        
        ## Make sure value is in range
        if typ in [LIB.TYPE_INT8, LIB.TYPE_UNS8, LIB.TYPE_INT16, LIB.TYPE_UNS16, LIB.TYPE_INT32, LIB.TYPE_UNS32, LIB.TYPE_FLT64]:
            (minval, maxval, stepval) = self.getParamRange(param)
            if value < minval:
                if autoCorrect:
                    value = minval
                    #print "Warning: Clipped value to %s" % str(value)
                else:
                    raise Exception("Minimum value for parameter is %s (requested %s)" % (str(minval), str(value)))
            if value > maxval:
                if autoCorrect:
                    value = maxval
                    #print "Warning: Clipped value to %s" % str(value)
                else:
                    raise Exception("Maximum value for parameter is %s (requested %s)" % (str(maxval), str(value)))
            if stepval != 0:
                inc = (value - minval) / stepval
                if (inc%1.0) != 0.0:
                    if autoCorrect:
                        value = minval + round(inc) * stepval
                        #print "Warning: Quantized value to %s" % str(value)
                    else:
                        raise Exception("Value for parameter must be in increments of %s (requested %s)" % (str(stepval), str(value)))
        elif typ == LIB.TYPE_CHAR_PTR:
            count = self._getParam(param, LIB.ATTR_COUNT)
            if len(value) > count:
                raise Exception("Enum value %d is out of range for parameter" % value)
        #print "   PVCam setParam checked value"
            
        ## Set value
        #print "pvcam setting parameter", paramName
        val = mkCObj(typ, value)
        self.call('pl_set_param', self.hCam, param, byref(val))
        
        if param in self.enumTable:
            val = self.enumTable[param][1][val.value]
        else:
            val = val.value
        
        self.paramValues[paramName] = val
        
        ## Setting parameter may have changed bounds on other variables
        for k in self.paramAttrs[paramName][3]:
            bounds = self.getParamRange(k)
            self.paramAttrs[k][0] = bounds
        
        ret = OrderedDict()
        ret[paramName] = val
            
        ## Setting parameter may have changed the value of other parameters
        if paramName in self.paramValueDeps:
            for k in self.paramValueDeps[paramName]:
                oldVal = self.paramValues[k]
                del self.paramValues[k]
                newVal = self.getParam(k)
                if oldVal != newVal:
                    ret[k] = newVal
        
        return (ret, True)
        #print "   PVCam setParam set done."

    def _setLocalParam(self, param, value, autoCorrect=True):
        """Set a parameter that is stored locally; no communication with camera needed (until camera restart)"""
        if param in self.paramAttrs:  ## check writable flag, bounds
            rules = self.paramAttrs[param]
            
            ## Sanity checks
            if not rules[1]:
                raise Exception('Parameter %s is not writable.' % param)
            if type(rules[0]) is list:
                if value not in rules[0]:
                    raise Exception('Value %s (type %s) not allowed for parameter %s. Options are: %s (type %s)' % (str(value), str(type(value)), param, rules[0], str(type(rules[0][0]))))
            elif type(rules[0]) is tuple:
                minval, maxval, stepval = rules[0]
                if minval is not None and value < minval:
                    if autoCorrect:
                        value = minval
                    else:
                        raise Exception('Value %s not allowed for parameter %s. Range is: %s' % (str(value), param, rules[0]))
                elif maxval is not None and value > maxval:
                    if autoCorrect:
                        value = maxval
                    else:
                        raise Exception('Value %s not allowed for parameter %s. Range is: %s' % (str(value), param, rules[0]))
                
                if stepval is not None and stepval > 0:
                    inc = (value - minval) / stepval
                    if (inc%1.0) != 0.0:
                        if autoCorrect:
                            value = minval + round(inc) * stepval
                            #print "Warning: Quantized value to %s" % str(value)
                        else:
                            raise Exception("Value for parameter %s must be in increments of %s (requested %s)" % (param, str(stepval), str(value)))
        
        self.paramValues[param] = value
        return ({param:value}, True)


    def _getRegion(self, region=None, binning=None):
        """Create a Region object based on current settings."""
        if region is None: region = self.getParam('region')
        if binning is None: binning = self.getParam('binning')
        rgn = LIB.rgn_type(region[0], region[2]+region[0]-1, binning[0], region[1], region[3]+region[1]-1, binning[1])
        rgn.width = int(region[2] / binning[0])
        rgn.height = int(region[3] / binning[1])
        #print region, binning, rgn.s1, rgn.s2, rgn.p1, rgn.p2, rgn.width, rgn.height
        return rgn
        #return Region(region, binning)

    def acquire(self, frames=None):
        """Acquire a specific number of frames."""
        if self.mode != 0:
            raise Exception("Camera is not ready to start new acquisition")
            
        exposure = self.getParam('exposure')
        ## Convert exposure to indexed value
        exp = self._parseExposure(exposure)
        expMode = self.exposureMode()
        
        rgn = self._getRegion()
        if frames is None:
            self.buf = numpy.empty((rgn.height, rgn.width), dtype=numpy.uint16)
            frames = 1
        else:
            self.buf = numpy.empty((frames, rgn.height, rgn.width), dtype=numpy.uint16)
        res = self.call('pl_exp_setup_seq', self.hCam, frames, 1, rgn, expMode, exp)
        #res = LIB.pl_exp_setup_seq(self.hCam, frames, 1, rgn, expMode, exp)
        ssize = res[6]
        
        if len(self.buf.data) != ssize:
            raise Exception('Created wrong size buffer! (%d != %d) Error: %s' %(len(self.buf.data), ssize, self.pvcam.error()))
        self.call('pl_exp_start_seq', self.hCam, self.buf.ctypes.data)   ## Warning: this memory is not locked, may cause errors if the system starts swapping.
        #LIB.pl_exp_start_seq(self.hCam, self.buf.ctypes.data)   ## Warning: this memory is not locked, may cause errors if the system starts swapping.
        self.mode = 1
        while True:
            ret = self.call('pl_exp_check_status', self.hCam)
            #ret = LIB.pl_exp_check_status(self.hCam)
            status = ret[1]
            bcount = ret[2]
            if status in [LIB.READOUT_COMPLETE, LIB.READOUT_NOT_ACTIVE]:
                break
            elif status == LIB.READOUT_FAILED:
                raise Exception("Readout failed: " + self.pvcam.error())
            time.sleep(exposure * 0.5)
        self.mode = 0
        return self.buf.transpose((0, 2, 1))

    def _parseExposure(self, exp):
        ## This function should make use of PARAM_EXP_RES, but it doesn't seem to work on Q57!
        #minexp = self.getParam(PARAM_MIN_EXP_TIME)
        #if exp < minexp:
        #    raise Exception("Exposure time is less than effective minimum (%f < %f)" % (exp, minexp))
        return int(exp * 1000.)
        

    def start(self):
        """Start continuous frame acquisition.

        Return a buffer into which frames will be written as they are acquired.
        Use lastFrame() to detect the arrival of new frames."""
        if self.mode != 0:
            raise Exception("Camera is not ready to start new acquisition")
        #assert(frames > 0)
        self._assertParamAvailable(LIB.PARAM_CIRC_BUFFER)
        
        exposure = self.getParam('exposure')
        ## Convert exposure to indexed value
        exp = self._parseExposure(exposure)
        expMode = self.exposureMode()
        rgn = self._getRegion()
        ringSize = self.getParam('ringSize')
        
        self.frameSize = rgn.width * rgn.height * 2
        self.buf = numpy.ascontiguousarray(numpy.empty((ringSize, rgn.height, rgn.width), dtype=numpy.uint16))
        
        res = self.call('pl_exp_setup_cont', self.hCam, 1, rgn, expMode, exp, buffer_mode=LIB.CIRC_OVERWRITE)
        #res = LIB.pl_exp_setup_cont(self.hCam, 1, rgn, expMode, exp, buffer_mode=LIB.CIRC_OVERWRITE)
        ssize = res[5]
        ssize = ssize*ringSize
        #print "   done"
        if len(self.buf.data) != ssize:
            raise Exception('Created wrong size buffer! (%d != %d) Error: %s' %(len(self.buf.data), ssize, self.pvcam.error()))
        self.call('pl_exp_start_cont', self.hCam, self.buf.ctypes.data, ssize)   ## Warning: this memory is not locked, may cause errors if the system starts swapping.

        self.mode = 2

        return self.buf.transpose((0, 2, 1))

    def exposureMode(self):
        """Return the exposure mode enum value to use based on the triggerMode parameter"""
        tm = self.getParam('triggerMode')
        if tm == 'Normal':
            return LIB.TIMED_MODE
        elif tm == 'TriggerStart':
            return LIB.TRIGGER_FIRST_MODE
        elif tm == 'Strobe':
            return LIB.STROBED_MODE
        elif tm == 'Bulb':
            return LIB.BULB_MODE
        else:
            raise Exception('Unknown trigger mode %s.' % tm)

    def lastFrame(self):
        """Return the index of the last frame transferred."""
        assert(self.buf is not None)
        try:
            frame = self.call('pl_exp_get_latest_frame', self.hCam)[1]
            #frame = LIB.pl_exp_get_latest_frame(self.hCam)[1]
        except Exception as ex:
            # if sys.exc_info()[1][1] == 3029:  ## No frame is ready yet (?)
            #     return None
            if ex.args[1] == 38:   # No frame ready yet
                return None
            else:
                raise
        if frame is None:
            return None
        index = (frame - self.buf.ctypes.data) / self.frameSize
        if index < 0 or index > (self.buf.shape[0]-1):
            print("Warning: lastFrame got %d!" % index)
            return None
        return index

    def stop(self):
        if self.mode == 1:
            self.call('pl_exp_abort', self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
            #LIB.pl_exp_abort(self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
        elif self.mode == 2:
            self.call('pl_exp_stop_cont', self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
            #LIB.pl_exp_stop_cont(self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
        self.mode = 0
        self.buf = None ## clear out array

    def getParamRange(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        #typ = self.getParamType(param)

        minval = self._getParam(param, LIB.ATTR_MIN)
        maxval = self._getParam(param, LIB.ATTR_MAX)
        stepval = self._getParam(param, LIB.ATTR_INCREMENT)

        return (minval, maxval, stepval)

    def getParamType(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        return self._getParam(param, LIB.ATTR_TYPE)

    def getParamTypeName(self, param):
        param = self.pvcam.paramFromString(param)
        typ = self.getParamType(param)
        return self.pvcam.typeToString(typ)

    def getEnumList(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        if self.getParamType(param) != LIB.TYPE_ENUM:
            raise Exception('Parameter is not enum type.')
        num = self._getParam(param, LIB.ATTR_COUNT)
        names = []
        vals = []
        for i in range(0, num):
            ret = self.call('pl_enum_str_length', self.hCam, param, i)
            #ret = LIB.pl_enum_str_length(self.hCam, param, i)
            slen = ret[3]
            strn = create_string_buffer(b'\0' * (slen))
            val = c_int()
            self.call('pl_get_enum_param', self.hCam, param, i, byref(val), strn, c_ulong(slen))
            #LIB.pl_get_enum_param(self.hCam, param, i, byref(val), strn, c_ulong(slen))
            names.append(strn.value)
            vals.append(val.value)
        return (names, vals)


    def _assertCameraOpen(self):
        if not self.isOpen:
            raise Exception("Camera is not open.")
    
    def paramAvailable(self, param):
        try:
            param = self.pvcam.paramFromString(param)
            #param = self.pvcam.param(param)
            self._assertCameraOpen()
            return self._getParam(param, LIB.ATTR_AVAIL) > 0
        except:
            sys.excepthook(*sys.exc_info())
            print("==============================================")
            print("Error checking availability of parameter %s" % param)
            return False
            
    def _assertParamAvailable(self, param):
        if not self.paramAvailable(param):
            raise Exception("Parameter %s is not available.", str(param))
        
    def paramWritable(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        access = self._getParam(param, LIB.ATTR_ACCESS)
        return access in [LIB.ACC_WRITE_ONLY, LIB.ACC_READ_WRITE]
        
    def paramReadable(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        access = self._getParam(param, LIB.ATTR_ACCESS)
        return access in [LIB.ACC_READ_ONLY, LIB.ACC_READ_WRITE]
        
    def _assertParamWritable(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        access = self._getParam(param, LIB.ATTR_ACCESS)
        if access in [LIB.ACC_EXIST_CHECK_ONLY, LIB.ACC_READ_ONLY]:
            raise Exception("Parameter is not writable.")
        elif access not in [LIB.ACC_WRITE_ONLY, LIB.ACC_READ_WRITE]:
            raise Exception("Unknown access check value!")

    def _assertParamReadable(self, param):
        param = self.pvcam.paramFromString(param)
        self._assertParamAvailable(param)
        access = self._getParam(param, LIB.ATTR_ACCESS)
        if access in [LIB.ACC_EXIST_CHECK_ONLY, LIB.ACC_WRITE_ONLY]:
            raise Exception("Parameter is not readable.")
        elif access not in [LIB.ACC_READ_WRITE, LIB.ACC_READ_ONLY]:
            raise Exception("Unknown access check value!")
    
    def _getParam(self, param, attr, typ=None):
        """Gets parameter/attribute combination. Automatically handles type conversion."""
        #param = self.pvcam.paramFromString(param)
        if typ is None:
            typs = {
                LIB.ATTR_ACCESS: LIB.TYPE_UNS16,
                LIB.ATTR_AVAIL: LIB.TYPE_BOOLEAN,
                LIB.ATTR_COUNT: LIB.TYPE_UNS32,
                LIB.ATTR_TYPE: LIB.TYPE_UNS16
            }
            if attr in typs:
                typ = typs[attr]
            else:
                typ = self.getParamType(param)
        val = mkCObj(typ)
        self.call('pl_get_param', self.hCam, param, attr, byref(val))
        #LIB.pl_get_param(self.hCam, param, attr, byref(val))

        ## If this is an enum, return the string instead of the value
        if typ == LIB.TYPE_ENUM:
            name = self.enumTable[param][1][val.value]
            
            #names = self.getEnumList(param)
            #print "names:", names, "value:", val.value
            #name = [names[0][i] for i in range(len(names)) if names[1][i] == val.value][0]
            return name
            
        return val.value

    #def listTriggerModes(self):
        #return {
            #'Normal': TIMED_MODE,
            #'Trigger First': TRIGGER_FIRST_MODE,
            #'Strobed': STROBED_MODE,
            #'Bulb': BULB_MODE
        #}
    
        
            
    def _buildEnumTable(self):
        """Builds dicts that link enum names to their values for each parameter."""
        enums = {}
        plist = self.pvcam.listParams(allParams=True)
        #print plist
        for n in plist:
            if not self.paramAvailable(n):
                continue
            typ = self.getParamType(n)
            if typ != LIB.TYPE_ENUM:
                continue
            enum = self.getEnumList(n)
            enums[n] = (dict(list(zip(enum[0], enum[1]))), dict(list(zip(enum[1], enum[0]))))
            paramId = self.pvcam.paramFromString(n)
            enums[paramId] = enums[n]
            
        return enums
        
    def _buildParamList(self):
        """Builds the list of attributes for each remote parameter"""
        plist = self.pvcam.listParams()
        rem = ['ADC_OFFSET']  ## Set by manufacturer; do not change.
        for r in rem:
            if r in plist:
                plist.remove(r)
        plist = list(filter(self.paramAvailable, plist))
        if len(plist) == 0:
            raise Exception('PVCam reported that camera %s has no parameters (this is bad; try restarting your camera)' % self.name)
        params = OrderedDict()
        
        numTypes = [LIB.TYPE_INT8, LIB.TYPE_UNS8, LIB.TYPE_INT16, LIB.TYPE_UNS16, LIB.TYPE_INT32, LIB.TYPE_UNS32, LIB.TYPE_FLT64]
        for p in plist:
            typ = self.getParamType(p)
            if typ in numTypes:
                (minval, maxval, stepval) = self.getParamRange(p)
                if stepval == 0:
                    vals = (minval, maxval, None)
                else:
                    vals = (minval, maxval, stepval)
            elif typ == LIB.TYPE_ENUM:
                #vals = self.getEnumList(p)[0]
                vals = list(self.enumTable[p][0].keys())
            elif typ == LIB.TYPE_BOOLEAN:
                vals = [True, False]
            else:
                vals = None
            params[p] = [vals, self.paramWritable(p), self.paramReadable(p), []]
        return params


#class Region(Structure):
    #_fields_ = [
        #('s1', c_ushort),
        #('s2', c_ushort),
        #('sbin', c_ushort),
        #('p1', c_ushort),
        #('p2', c_ushort),
        #('pbin', c_ushort)
    #]
    
    #def __init__(self, *args):
        #if len(args) == 6:
            #Structure.__init__(self, *args)
        #else:
            ##print "creating region:", args
            #rgn = args[0][:]
            #if type(args[1]) is types.IntType:
                #bin = [args[1], args[1]]
            #else:
                #bin = args[1][:]
            #assert( hasattr(rgn, '__len__') and len(rgn) == 4 )
            #assert( hasattr(bin, '__len__') and len(bin) == 2 )
            ### Quantize region size based on binning parameter
            ## (is this needed at all?)
            ##rgn[2] = rgn[0] + (int((rgn[2]-rgn[0]+1)/bin[0]) * bin[0]) - 1
            ##rgn[3] = rgn[1] + (int((rgn[3]-rgn[1]+1)/bin[1]) * bin[1]) - 1
            #Structure.__init__(self, rgn[0], rgn[2], bin[0], rgn[1], rgn[3], bin[1])
            #self.width, self.height = self.size()
            
    #def size(self):
        #return ((self.s2-self.s1+1) / self.sbin, (self.p2-self.p1+1) / self.pbin)


def mkCObj(typ, value=None):
    typs = {
        LIB.TYPE_INT8: c_byte, 
        LIB.TYPE_UNS8: c_ubyte,
        LIB.TYPE_INT16: c_short,
        LIB.TYPE_UNS16: c_ushort,
        LIB.TYPE_INT32: c_int,
        LIB.TYPE_UNS32: c_uint,
        LIB.TYPE_FLT64: c_double,
        LIB.TYPE_ENUM: c_ushort,
        LIB.TYPE_BOOLEAN: c_ushort,
        LIB.TYPE_CHAR_PTR: c_char_p, ## This is likely to cause bugs--we need to use create_string_buffer
        LIB.TYPE_VOID_PTR: c_void_p,
        LIB.TYPE_VOID_PTR_PTR: c_void_p
    }
    if typ not in typs:
        raise Exception("Unknown type %d" % typ)
    if value is None:
        return typs[typ]()
    else:
        return typs[typ](value)


init()
