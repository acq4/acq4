# -*- coding: utf-8 -*-
from ctypes import *
import sys, numpy, time, types
#import lib.util.cheader as cheader
from clibrary import *
from advancedTypes import OrderedDict

__all__ = ['PVCam']


### Load header files, open DLL
headerFiles = [
    "C:\Program Files\Photometrics\PVCam32\SDK\inc\master.h",
    "C:\Program Files\Photometrics\PVCam32\SDK\inc\pvcam.h"
]
HEADERS = CParser(headerFiles, cache='pvcam_headers.cache', copyFrom=winDefs())
LIB = CLibrary(windll.Pvcam32, HEADERS, prefix='pl_')


### Default configuration parameters. 
### All cameras use the parameters under 'ALL'
### If a camera model matches another key, then those values override.
### format for each camera is [ (paramName, value, range, writable, readable, deps), ... ]

cameraDefaults = {
    'ALL': [
        ('READOUT_PORT', 0),  ## Only option for Q57, fastest for QuantEM
        ('SPDTAB_INDEX', 0),
        ('GAIN_INDEX', 3),
        ('PMODE', LIB.PMODE_NORMAL),  ## PMODE_FT ?
        ('SHTR_OPEN_MODE', LIB.OPEN_PRE_SEQUENCE),
        ('CLEAR_MODE', LIB.CLEAR_PRE_EXPOSURE),
        ('CLEAR_CYCLES', 2),
    ],
        
    'QUANTEM:512SC': [
        ('SPDTAB_INDEX', 0),  ## Fastest option for QM512
        ('CLEAR_MODE', LIB.CLEAR_PRE_SEQUENCE),  ## Overlapping mode for QuantEM cameras
        ('GAIN_INDEX', 2),
        ('binningX', 1, range(1,9)),
        ('binningY', 1, range(1,9)),
    ],
    
    'Quantix57': [
        ('SPDTAB_INDEX', 2),  ## Fastest option for Q57
        ('binningX', 1, [2**x for x in range(9)]),
        ('binningY', 1, [2**x for x in range(9)]),
    ],
}




### List of parameters we want exposed to the outside
### (We could just list all parameters from the DLL, but it turns out there are many that we do not 
### want to expose)
externalParams = [
    'READOUT_PORT',
    'SPDTAB_INDEX',
    'BIT_DEPTH',
    'GAIN_INDEX',
    'GAIN_MULT_ENABLE',
    'GAIN_MULT_FACTOR',
    'INTENSIFIER_GAIN',
    #'EXPOSURE_MODE',
    'PREFLASH',
    'PIX_TIME',
    'CLEAR_MODE',
    'CLEAR_CYCLES',
    'SHTR_OPEN_MODE',
    'SHTR_OPEN_DELAY',
    'PIX_SER_SIZE',
    'PIX_PAR_SIZE',
    'ANTI_BLOOMING',
    'TEMP',
    'TEMP_SETPOINT',
    'COOLING_MODE',
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

        #self.pvcam = windll.Pvcam32
        if _PVCamClass.PVCAM_CREATED:
            raise Exception("Will not create another pvcam instance--use the pre-existing PVCam object.")
        if LIB.pvcam_init() < 1:
            raise Exception("Could not initialize pvcam library (pl_pvcam_init): %s" % self.error())
        # This should happen before every new exposure (?)
        if LIB.exp_init_seq() < 1:
            raise Exception("Could not initialize pvcam library (pl_exp_init_seq): %s" % self.error())
        _PVCamClass.PVCAM_CREATED = True
        
        #self.paramList = [
        #    'SPDTAB_INDEX',
        #    'BIT_DEPTH',
        #    'GAIN_INDEX',
        #    'GAIN_MULT_ENABLE',
        #    'GAIN_MULT_FACTOR',
        #    'INTENSIFIER_GAIN',
        #    #'EXPOSURE_MODE',  ## this is mostly exposed through triggerMode
        #    'PREFLASH',
        #    'PIX_TIME',
        #    'CLEAR_MODE',
        #    'CLEAR_CYCLES',
        #    'SHTR_OPEN_MODE',
        #    'SHTR_OPEN_DELAY',
        #    'PIX_SER_SIZE',
        #    'PIX_PAR_SIZE',
        #    'SER_SIZE',
        #    'PAR_SIZE',
        #    'ANTI_BLOOMING',
        #    'TEMP',
        #    'TEMP_SETPOINT',
        #    'COOLING_MODE',
        #]
        
        global externalParams
        
        self.paramTable = {}
        for p in externalParams:
            self.paramTable[p] = self.paramFromString(p)
        
        

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
            cName = create_string_buffer('\0' * LIB.CAM_NAME_LEN)
            if LIB.cam_get_name(i, cName)() < 1:
                raise Exception("Error getting name for camera %d: %s" % (i, self.error()))
            cams.append(cName.value)
        return cams

    def getCamera(self, cam):
        if not self.cams.has_key(cam):
            self.cams[cam] = _CameraClass(cam, self)
        return self.cams[cam]
    
    #def __getattr__(self, attr):
    #    if hasattr(self.pvcam, attr):
    #        return lambda *args: self.call(attr, *args)
    #    else:
    #        raise NameError

    def call(self, func, *args, **kargs):
        fn = LIB('functions', func)
        res = fn(*args, **kargs)
        if res() < 1:
            raise Exception("Function '%s%s' failed: %s" % (func, str(args), self.error()), self.errno())
        return res

    def errno(self):
        erc = LIB.error_code()()
        return erc

    def error(self, erno=None):
        if erno is None:
            erno = LIB.error_code()()
        err = create_string_buffer('\0'*LIB.ERROR_MSG_LEN)
        LIB.error_message(erno, err)
        return "%d: %s" % (erno, err.value)

    def __del__(self):
        self.quit()

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

    #def param(self, pName):
    #    if isinstance(pName, basestring):
    #        pName = 'PARAM_'+pName
    #        if pName in self.defs:
    #            return self.defs[pName]
    #        else:
    #            raise Exception('No parameter named %s' % pName)
    #    else:
    #        return pName
    #
    #def attr(self, pName):
    #    if isinstance(pName, basestring):
    #        pName = 'ATTR_'+pName
    #        if pName in self.defs:
    #            return self.defs[pName]
    #        else:
    #            raise Exception('No parameter named %s' % pName)
    #    else:
    #        return pName
    #
    #def paramName(self, param):
    #    for p in self.listParams():
    #        if self.defs[p] == param:
    #            return p
    #
    #def attrName(self, attr):
    #    for p in self.defs:
    #        if p[:5] == 'ATTR_' and self.defs[p] == attr:
    #            return p
    #
    #def typeName(self, typ):
    #    for p in self.defs:
    #        if p[:5] == 'TYPE_' and self.defs[p] == typ:
    #            return p

    def listParams(self):
        #return [x[6:] for x in self.defs if x[:6] == 'PARAM_']
        return self.paramTable.keys()
    
    def paramFromString(self, p):
        """Return the driver's param ID for the given parameter name."""
        
        if isinstance(p, basestring):
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
        
    #def typeFromString(self, p):
    #    """Return the driver's type ID for the given type name."""
    #    return p
    #        
    #def typeToString(self, p):
    #    """Return the type name given the driver's type ID."""
    #    return p
            
        

class _CameraClass:
    def __init__(self, name, pvcam):
        self.name = name
        self.pvcam = pvcam
        self.isOpen = False
        self.open()
        
        #self.exposure = 0.01
        #self.binning = [1, 1]
        self.mode = 0
        #self.frameSize = 1
        #self.ringSize = 10
        self.buf = None
        
        self.params = {}
        self.groupParams = {
            'binning': ['binningX', 'binningY'],
            'region': ['regionX', 'regionY', 'regionW', 'regionH'],
            'sensorSize': ['SER_SIZE', 'PAR_SIZE'] 
        }
        
        self.paramList = OrderedDict()
        for p in ['exposure', 'binningX', 'binningY', 'regionX', 'regionY', 'regionW', 'regionH', 'triggerMode']:
            ## get these in the list now so they show up first
            self.paramList[p] = None
            
        self.paramList.update(self.buildParamList())  ## list of acceptable values for each parameter
        
        size = self.getParam('sensorSize')
        self.params = {  ## list of current values for parameters not handled by driver
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
        
        
        self.paramList.update({
            'binningX': [(1, size[0], 1), True, True, []],  
            'binningY': [(1, size[1], 1), True, True, []],
            'exposure': [(0, None, None), True, True, []],
            'triggerMode': [['Normal', 'TriggerStart', 'Strobe', 'Bulb'], True, True, []],
            'regionX': [(0, size[0]-1, 1), True, True, []],
            'regionY': [(0, size[1]-1, 1), True, True, []],
            'regionW': [(1, size[0], 1), True, True, []],
            'regionH': [(1, size[1], 1), True, True, []],
            'ringSize': [(2, None, 1), True, True, []],
        })
        
        self.initCam()
            
            
        
    def buildParamList(self):
        plist = self.pvcam.listParams()
        plist = filter(self.paramAvailable, plist)
        rem = ['ADC_OFFSET']  ## Set by manufacturer; do not change.
        for r in rem:
            if r in plist:
                plist.remove(r)
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
                vals = self.getEnumList(p)[0]
            elif typ == LIB.TYPE_BOOLEAN:
                vals = [True, False]
            else:
                vals = None
            params[p] = [vals, self.paramWritable(p), self.paramReadable(p), []]
        
        return params

    def __del__(self):
        self.close()

    def open(self):
        ## Driver bug; try opening twice.
        try:
            self.hCam = LIB.cam_open(self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
        except:
            self.hCam = LIB.cam_open(self.name, o_mode=LIB.OPEN_EXCLUSIVE)[2]
        self.isOpen = True

    def close(self):
        if self.isOpen:
            #self.pvcam.pl_exp_abort(CCS_HALT_CLOSE_SHUTTER)
            self.call('cam_close')
            self.isOpen = False
            
    def call(self, fn, *args, **kargs):
        return self.pvcam.call(fn, self.hCam, *args, **kargs)

    def initCam(self, params=None):
        buf = create_string_buffer('\0' * LIB.CCD_NAME_LEN)
        camType = self.call('get_param', LIB.PARAM_CHIP_NAME, LIB.ATTR_CURRENT, buf)[3]
        #print "Camera type:", camType
        
        ## Implement default settings for this camera model
        defaults = OrderedDict([(p[0], p[1]) for p in cameraDefaults['ALL']])
        ranges = dict([(p[0], p[2:]) for p in cameraDefaults['ALL']])
        
        if camType in cameraDefaults:
            camDefaults = OrderedDict([(p[0], p[1]) for p in cameraDefaults[camType]])
            camRanges = dict([(p[0], p[2:]) for p in cameraDefaults[camType]])
            defaults.update(camDefaults)
            ranges.update(camRanges)
        
        for k,v in ranges.items():
            #print self.paramList[k], k, v
            for i in range(len(v)):
                self.paramList[k][i] = v[i]
        
        self.setParams(defaults)
            
        
    #def getEnum(self, param):
    #    l = self.getEnumList(param)
    #    v = self.getParam(param)
    #    return l[1].index(v)
    #    
    #def setEnum(self, param, val):
    #    l = self.getEnumList(param)
    #    if val >= len(l[0]):
    #        raise Exception("Invalid value for %s" % paramName(param))
    #    self.setParam(param, l[1][val])
        

    def listParams(self, params=None):
        if params is None:
            return self.paramList.copy()
        else:
            if isinstance(params, basestring):
                try:
                    return self.paramList[params]
                except KeyError:
                    raise Exception("No parameter named '%s'" % params)
                
            plist = params
            params = {}
            for p in plist:
                try:
                    params[p] = self.paramList[p]
                except KeyError:
                    raise Exception("No parameter named '%s'" % p)
            return params


            
    def getParams(self, params, asList=False):
        #if isinstance(params, list):
        #    return [self.getParam(p) for p in params]
        #elif isinstance(params, dict):
        #    return dict([(p, self.getParam(p)) for p in params])
        #else:
        #    raise Exception('getParams requires list or dict as argument')
        if asList:
            return [self.getParam(p) for p in params]
        else:
            return OrderedDict([(p, self.getParam(p)) for p in params])

    def getParam(self, param):
        ## Make sure parameter exists on this hardware and is readable
        #print "GetParam:", param
        
        if param in self.groupParams:
            return self.getParams(self.groupParams[param], asList=True)
        
        if param in self.params:
            return self.params[param]
                        
        param = self.pvcam.paramFromString(param)
        self._assertParamReadable(param)
        return self._getParam(param, LIB.ATTR_CURRENT)
        
    def setParams(self, params, autoCorrect=True):
        ###   - PARAM_BIT_DEPTH, PARAM_PIX_TIME, and PARAM_GAIN_INDEX(ATTR_MAX)
        ###     are determined by setting PARAM_READOUT_PORT and PARAM_SPDTAB_INDEX 
        ###   - PARAM_GAIN_INDEX must be set AFTER setting PARAM_SPDTAB_INDEX
        #keys = params.keys()
        #for k in ['PARAM_READOUT_PORT', 'PARAM_SPDTAB_INDEX']:
            #if k in keys:
                #keys.remove(k)
                #keys = [k] + keys
        #for p in keys:
            #self.setParam(p, params[p], **kargs)
        
        res = {}
        if isinstance(params, dict):
            plist = params.items()
        else:
            plist = params
            
        for p, v in plist:
            res[p] = self.setParam(p, v, autoCorrect)
        return res
        
    def setParam(self, param, value, autoCorrect=True):
        ## Make sure parameter exists on this hardware and is writable
        #print "PVCam setParam", param, value
        
        if param in self.groupParams:
            return self.setParams(zip(self.groupParams[param], value))
        
        
        if param in self.params:
            return self._setLocalParam(param, value, autoCorrect)
        
        param = self.pvcam.paramFromString(param)
        self._assertParamReadable(param)

        if isinstance(value, basestring):
            try:
                value = getattr(LIB, value)
            except:
                raise Exception("Unrecognized value '%s'. Options are: %s" % (value, str(self.pvcam.defs.keys())))

        
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
        #elif typ == TYPE_ENUM:
        #    count = self._getParam(param, ATTR_COUNT)
        #    if value > (count-1):
        #        raise Exception("Enum value %d is out of range for parameter" % value)
        elif typ == LIB.TYPE_CHAR_PTR:
            count = self._getParam(param, LIB.ATTR_COUNT)
            if len(value) > count:
                raise Exception("Enum value %d is out of range for parameter" % value)
        #print "   PVCam setParam checked value"
            
        ## Set value
        val = mkCObj(typ, value)
        LIB.pl_set_param(self.hCam, param, byref(val))
        return val
        #print "   PVCam setParam set done."

    def _setLocalParam(self, param, value, autoCorrect=True):
        """Set a parameter that is stored locally; no communication with camera needed (until camera restart)"""
        if param in self.paramList:  ## check writable flag, bounds
            rules = self.paramList[param]
            
            ## Sanity checks
            if not rules[1]:
                raise Exception('Parameter %s is not writable.' % param)
            if type(rules[0]) is list:
                if value not in rules[0]:
                    raise Exception('Value %s not allowed for parameter %s. Options are: %s' % (str(value), param, rules[0]))
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
        
        self.params[param] = value
        return value


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
        res = LIB.pl_exp_setup_seq(self.hCam, frames, 1, rgn, expMode, exp)
        ssize = res[6]
        
        if len(self.buf.data) != ssize:
            raise Exception('Created wrong size buffer! (%d != %d) Error: %s' %(len(self.buf.data), ssize, self.pvcam.error()))
        LIB.pl_exp_start_seq(self.hCam, self.buf.ctypes.data)   ## Warning: this memory is not locked, may cause errors if the system starts swapping.
        self.mode = 1
        while True:
            ret = LIB.pl_exp_check_status(self.hCam)
            status = ret[1]
            bcount = ret[2]
            if status in [LIB.READOUT_COMPLETE, LIB.READOUT_NOT_ACTIVE]:
                break
            elif status == LIB.READOUT_FAILED:
                raise Exception("Readout failed: " + self.pvcam.error())
            time.sleep(exposure * 0.5)
        self.mode = 0
        return self.buf

    def _parseExposure(self, exp):
        ## This function should make use of PARAM_EXP_RES, but it doesn't seem to work on Q57!
        #minexp = self.getParam(PARAM_MIN_EXP_TIME)
        #if exp < minexp:
        #    raise Exception("Exposure time is less than effective minimum (%f < %f)" % (exp, minexp))
        return int(exp * 1000.)
        

    def start(self):
        """Start continuous frame acquisition."""
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
        
        res = LIB.pl_exp_setup_cont(self.hCam, 1, rgn, expMode, exp, buffer_mode=LIB.CIRC_OVERWRITE)
        ssize = res[5]
        ssize = ssize*ringSize
        #print "   done"
        if len(self.buf.data) != ssize:
            raise Exception('Created wrong size buffer! (%d != %d) Error: %s' %(len(self.buf.data), ssize, self.pvcam.error()))
        LIB.pl_exp_start_cont(self.hCam, self.buf.ctypes.data, ssize)   ## Warning: this memory is not locked, may cause errors if the system starts swapping.
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
            frame = LIB.pl_exp_get_latest_frame(self.hCam)[1]
        except:
            if sys.exc_info()[1][1] == 3029:  ## No frame is ready yet (?)
                return None
            else:
                raise
        if frame is None:
            return None
        index = (frame - self.buf.ctypes.data) / self.frameSize
        if index < 0 or index > (self.buf.shape[0]-1):
            print "Warning: lastFrame got %d!" % index
            return None
        return index

    def stop(self):
        if self.mode == 1:
            LIB.pl_exp_abort(self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
        elif self.mode == 2:
            LIB.pl_exp_stop_cont(self.hCam, LIB.CCS_CLEAR_CLOSE_SHTR)
        self.mode = 0

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
            ret = LIB.pl_enum_str_length(self.hCam, param, i)
            slen = ret[3]
            strn = create_string_buffer('\0' * (slen))
            val = c_int()
            LIB.pl_get_enum_param(self.hCam, param, i, byref(val), strn, c_ulong(slen))
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
            print "=============================================="
            print "Error checking availability of parameter %s" % param
            return False
            
    def _assertParamAvailable(self, param):
        if not self.paramAvailable(param):
            raise Exception("Parameter %s is not available.", self.pvcam.paramToString(param))
        
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
            if typs.has_key(attr):
                typ = typs[attr]
            else:
                typ = self.getParamType(param)
        val = mkCObj(typ)
        LIB.pl_get_param(self.hCam, param, attr, byref(val))
        return val.value

    #def listTriggerModes(self):
        #return {
            #'Normal': TIMED_MODE,
            #'Trigger First': TRIGGER_FIRST_MODE,
            #'Strobed': STROBED_MODE,
            #'Bulb': BULB_MODE
        #}
    
        


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
    if not typs.has_key(typ):
        raise Exception("Unknown type %d" % typ)
    if value is None:
        return typs[typ]()
    else:
        return typs[typ](value)


init()
