import time
from ctypes import *
import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))
from clibrary import *
from numpy import empty, uint16, ascontiguousarray, concatenate, newaxis
from pyqtgraph import graphicsWindows as gw
from PyQt4 import QtGui
from Mutex import Mutex, MutexLocker
import atexit
p = CParser('QCamApi.h', cache='QCamApi.h.cache', macros={'_WIN32': '', '__int64': ('long long')})
if sys.platform == 'darwin':
    dll = cdll.LoadLibrary('/Library/Frameworks/QCam.framework/QCam')
else:
    dll = windll.QCamDriver
lib = CLibrary(dll, p, prefix = 'QCam_')        #makes it so that functions in the header file can be accessed using lib.nameoffunction, ie: QCam_LoadDriver is lib.LoadDriver
                                                #also interprets all the typedefs for you....very handy
                                                #anything from the header needs to be accessed through lib.yourFunctionOrParamete
    
class QCamFunctionError(Exception):
    def __init__(self, value, message):
        self.value = value
        self.message = message
    def __str__(self):
        return repr(self.message)


def call(function, *args):
    a = function(*args)
    if a() != 0:
        for x in lib('enums', 'QCam_Err'):
            if lib('enums', 'QCam_Err')[x] == a():
                raise QCamFunctionError(a(), "There was an error running a QCam function. Error code = %s" %(x))
    else:
        return a
    
def quit():
    lib.Abort(handle)
    lib.SetStreaming(handle, 0)
    lib.CloseCamera(handle)
    lib.ReleaseDriver()
    print 'Closing down...'
atexit.register(quit)

def loadDriver():
    call(lib.LoadDriver)
 
def releaseDriver():
    call(lib.ReleaseDriver)
    
def listCameras():
    number = c_ulong(10)
    L = lib.CamListItem * 10
    l = L()
    call(lib.ListCameras, l, number)
    b = []
    for x in list(l)[:number.value]:
        b.append(x.cameraId)
    return b
 
def openCamera(cameraID): #opens the camera and returns the handle
    """Opens the chosen camera and returns the handle. Takes cameraID parameter."""
    a = call(lib.OpenCamera, cameraID, lib.Handle())
    return a[1] 
    
def mkFrame():
    s = call(lib.GetInfo, handle, lib.qinfImageSize)[2]
    f = lib.Frame()
    frame = ascontiguousarray(empty(s/2, dtype=uint16))
    f.pBuffer = frame.ctypes.data
    f.bufferSize = s
    return (f, frame)
    
def grabFrame():
    s = lib.GetInfo(handle, lib.qinfImageSize)[2]
    (f, frame) = mkFrame()
    call(lib.GrabFrame, handle, byref(f))
    w = call(lib.GetInfo, handle, lib.qinfCcdWidth)[2]
    frame.shape = (s/w, w)
    return frame

paramenums = {
    'qprmImageFormat': 'QCam_ImageFormat',
    'qprmPostProcessImageFormat': 'QCam_ImageFormat',
    'qprmSyncb': 'QCam_qcSyncb',
    'qprmReadoutSpeed': 'QCam_qcReadoutSpeed',
    'qprmColorWheel': 'QCam_qcWheelColor',
    'qprmTriggerType': 'QCam_qcTriggerType'
    }

parameters = {}
def listParams():
    """Fills in the 'parameters' dictionary with the state parameters available on the camera.
    The key is the name of the parameter, while the value is the range of possible values."""
    s = call(lib.ReadSettingsFromCam, handle)[1]
    s.size = sizeof(s)
    for x in lib('enums', 'QCam_Param'):
        if lib.GetParam(byref(s), getattr(lib, x))() == 0:
            try:
                try:
                    table = (c_ulong *32)()
                    r = call(lib.GetParamSparseTable, byref(s), getattr(lib,x), table, c_long(32))
                    parameters[x] = (list(r[2])[:r[3]])
                except QCamFunctionError, err:
                    if err.value == 1:  
                        min = call(lib.GetParamMin, byref(s), getattr(lib,x))[2]
                        max = call(lib.GetParamMax, byref(s), getattr(lib,x))[2]
                        parameters[x] = (min, max)
                    else: raise      
            except QCamFunctionError, err:
                if err.value == 1: pass    
                else: raise
    for x in lib('enums', 'QCam_ParamS32'):
        if lib.GetParamS32(byref(s), getattr(lib, x))() == 0:
            try:
                try:
                    table = (c_long *32)()
                    r = call(lib.GetParamSparseTableS32, byref(s), getattr(lib,x), table, c_long(32))
                    parameters[x] = (list(r[2])[:r[3]])
                except QCamFunctionError, err:
                    if err.value == 1:
                        min = call(lib.GetParamS32Min, byref(s), getattr(lib,x))[2]
                        max = call(lib.GetParamS32Max, byref(s), getattr(lib,x))[2]
                        parameters[x] = (min, max)
                    else: raise
            except QCamFunctionError, err:
                if err.value == 1: pass
                else: raise
    for x in lib('enums', 'QCam_Param64'):
        if lib.GetParam64(byref(s), getattr(lib, x))() == 0:
            try:
                try:
                    table = (c_ulonglong *32)()
                    r = call(lib.GetParamSparseTable64, byref(s), getattr(lib,x), table, c_long(32))
                    parameters[x] = (list(r[2])[:r[3]])
                except QCamFunctionError, err:
                    if err.value == 1:
                        min = call(lib.GetParam64Min, byref(s), getattr(lib,x))[2]
                        max = call(lib.GetParam64Max, byref(s), getattr(lib,x))[2]
                        parameters[x] = (min, max)
                    else: raise
            except QCamFunctionError, err:
                if err.value == 1:  pass
                else: raise
    parameters.pop('qprmExposure')
    parameters.pop('qprmOffset')
    for x in parameters: 
        if type(parameters[x]) == type([]):
            if x in paramenums: ## x is the name of the parameter
                print "Param: ", x, parameters[x]
                for i in range(len(parameters[x])): ## i is the index
                    a = parameters[x][i] ## a is the value
                    for b in lib('enums', paramenums[x]): # b is the number code for the parameter option
                        if lib('enums', paramenums[x])[b] == a:
                            parameters[x][i] = b
                            print "old: ", a, "new: ", parameters[x][i]


                    
camerainfo = {}
def getCameraInfo():
    for x in lib('enums', 'QCam_Info'):
        try:
            a = call(lib.GetInfo, handle, getattr(lib, x))
            camerainfo[x] = a[2]
        except QCamFunctionError, err:
            if err.value == 1:
                print "No info for: ", x
            else: raise
            
            
    

def getParam(param):
    s = call(lib.ReadSettingsFromCam, handle)[1]
    s.size = sizeof(s)
    if param in lib('enums', 'QCam_Param'):
        value = call(lib.GetParam, byref(s), getattr(lib, param))[2]
    elif param in lib('enums', 'QCam_ParamS32'):
        value = call(lib.SetParamS32, byref(s), getattr(lib, param))[2]
    elif param in lib('enums', 'QCam_Param64'):
        value = call(lib.SetParam64, byref(s), getattr(lib, param))[2]
    return value

def setParam(param, value):
    s = call(lib.ReadSettingsFromCam, handle)[1]
    if param in lib('enums', 'QCam_Param'):
        call(lib.SetParam, byref(s), getattr(lib, param), c_ulong(value))
    elif param in lib('enums', 'QCam_ParamS32'):
        call(lib.SetParamS32, byref(s), getattr(lib, param), c_long(value))
    elif param in lib('enums', 'QCam_Param64'):
        call(lib.SetParam64, byref(s), getattr(lib, param), c_ulonglong(value))
    m.lock()
    if stopsignal == True:
        m.unlock()
        call(lib.SendSettingsToCam, handle, byref(s))
    if stopsignal == False:
        m.unlock()
        call(lib.QueueSettings, handle, byref(s), null, lib.qcCallbackDone)

def getParams(*params):
    s = call(lib.ReadSettingsFromCam, handle)[1]
    dict = {}
    for param in params:
        if param in lib('enums', 'QCam_Param'):
            value = call(lib.GetParam, byref(s), getattr(lib, param))[2]
        elif param in lib('enums', 'QCam_ParamS32'):
            value = call(lib.GetParamS32, byref(s), getattr(lib, param))[2]
        elif param in lib('enums', 'QCam_Param64'):
            value = call(lib.GetParam64, byref(s), getattr(lib, param))[2]
        dict[param]=value
    return dict

def setParams(**params):
    s = call(lib.ReadSettingsFromCam, handle)[1]
    for param in params:
        if param in lib('enums', 'QCam_Param'):
            call(lib.SetParam, byref(s), getattr(lib, param), c_ulong(params[param]))
        elif param in lib('enums', 'QCam_ParamS32'):
            call(lib.SetParamS32, byref(s), getattr(lib, param), c_long(params[param]))
        elif param in lib('enums', 'QCam_Param64'):
            call(lib.SetParam64, byref(s), getattr(lib, param), c_ulonglong(params[param]))
    m.lock()
    if stopsignal == True:
        m.unlock()
        call(lib.SendSettingsToCam, handle, byref(s))
    if stopsignal == False:
        m.unlock()
        call(lib.QueueSettings, handle, byref(s), 0, lib.qcCallbackDone)
    


frames = []
arrays = []
i = 0
stopsignal = True
m = Mutex()

def start():
    global i, stopsignal
    m.lock()
    stopsignal = False
    i = 0
    m.unlock()
    call(lib.SetStreaming, handle, 1)
    for x in range(200):
        f, a = mkFrame()
        frames.append(f)
        arrays.append(a)
    for x in range(2):
        call(lib.QueueFrame, handle, frames[i], fnp1, lib.qcCallbackDone, 0, i)
        m.lock()
        i += 1
        m.unlock()
    
def callBack1(*args):
    global i, lastframe
    if args[2] != 0:
        for x in lib('enums', 'QCam_Err'):
            if lib('enums', 'QCam_Err')[x] == args[2]:
                raise QCamFunctionError(args[2], "There was an error during QueueFrame/Callback. Error code = %s" %(x))
    m.lock()
    lastframe = (args[1], arrays[args[1]]) ### Need to figure out a way to attach settings info (binning, exposure gain region and offset) to frame!!!
    if i != 199:
        i += 1
    else:
        i = 0
    if stopsignal == False:
        m.unlock()
        call(lib.QueueFrame, handle, frames[i], fnp1, lib.qcCallbackDone, 0, i)
    else:
        m.unlock()

def stop():
    global stopsignal
    m.lock()
    stopsignal = True
    call(lib.Abort, handle)
    m.unlock()

def lastFrame():
    global lastframe
    m.lock()
    a = lastframe
    m.unlock()
    return a 
    
    
loadDriver()
cameras = listCameras()
handle = openCamera(cameras[0])
fnp1 = lib.AsyncCallback(callBack1)
lastframe = (0,0)


#setParam(lib.qprmDoPostProcessing, 0)
#setParams(qprm64Exposure=10000000)
##setParams(qprmExposureRed=0, qprmExposureBlue=0)
#setParams(qprmReadoutSpeed=lib.qcReadout20M)
#
#setParams(qprmTriggerType=lib.qcTriggerFreerun, qprmImageFormat=lib.qfmtMono16)
#
#
#
#getCameraInfo()
#print camerainfo
#
#
#
#n = 0
#
#
#
#
#for i in range(5):
#    f, a = mkFrame()
#    frames.append(f)
#    arrays.append(a)
#    print "Queue frame..", id(f)
#    
#    print "Frame queued."
#   # time.sleep(0.3)

#time.sleep(1.0)
#print "starting app.."
#app = QtGui.QApplication([])
#print "app started."
#print a.shape, (camerainfo['qinfCcdWidth'], camerainfo['qinfCcdHeight'])
#a.shape = (camerainfo['qinfCcdHeight'], camerainfo['qinfCcdWidth'])
#print "create window"
#imw1 = gw.ImageWindow()
#imw1.setImage(a.transpose())
##imw1.setImage(concatenate([a.transpose()[newaxis] for a in arrays]))
#print "show window"
#imw1.show()
#
#print "Done."
#
#app.exec_()

