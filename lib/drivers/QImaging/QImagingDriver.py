
from ctypes import *
import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))
from clibrary import *
from numpy import empty
from pyqtgraph import graphicsWindows as gw
from PyQt4 import QtGui
import atexit
p = CParser('QCamApi.h', cache='QCamApi.h.cache')
if sys.platform == 'darwin':
    dll = cdll.LoadLibrary('/Library/Frameworks/QCam.framework/QCam')
else:
    dll = windll.QCamDriver
lib = CLibrary(dll, p, prefix = 'QCam_')        #makes it so that functions in the header file can be accessed using lib.nameoffunction, ie: QCam_LoadDriver is lib.LoadDriver
                                                #also interprets all the typedefs for you....very handy
                                                #anything from the header needs to be accessed through lib.yourFunctionOrParameter

def quit():
    lib.CloseCamera(handle)
atexit.register(quit)

def loadDriver():
    a = lib.LoadDriver()
    if a() != 0:
        raise Exception('There was an error loading the driver. Error code = ', a())

def releaseDriver():
    a = lib.ReleaseDriver()
    if a() != 0:
        raise Exception('There was an error releasing the driver. Error code = ', a())
        
def listCameras():
    number = c_ulong(10)
    L = lib.CamListItem * 10
    l = L()
    a = lib.ListCameras(l, number)
    if a() != 0:
        raise Exception('There was an error finding cameras. Error code = ', a())
    b = []
    for x in list(l)[:number.value]:
        b.append(x.cameraId)
    return b
 
def openCamera(cameraID): #opens the camera and returns the handle
    """Opens the chosen camera and returns the handle. Takes cameraID parameter."""
    a = lib.OpenCamera(cameraID, lib.Handle())
    if a() != 0:
        raise Exception('There was an error opening camera. Error code = ', a())
    return a[1] #possibly need to keep handle as a c type. use a.args[1] to do so
    
def mkFrame():
    s = lib.GetInfo(handle, lib.qinfImageSize)[2]
    f = lib.Frame()
    frame = empty(s, dtype=ubyte)
    f.pBuffer = frame.ctypes.data
    f.bufferSize = s
    return (f, frame)
    
def grabFrame():
    s = lib.GetInfo(handle, lib.qinfImageSize)[2]
    (f, frame) = mkFrame()
    lib.GrabFrame(handle, byref(f))
    w = lib.GetInfo(handle, lib.qinfCcdWidth)[2]
    frame.shape = (s/w, w)
    return frame

parameters = {}
def listParams():
    """Fills in the 'parameters' dictionary with the parameters available on the camera.
    The key is the name of the parameter, while the value is the range of possible values."""
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    for x in lib('enums', 'QCam_Param'): 
        if lib.IsParamSupported(handle, getattr(lib, x))() == 0:
            if lib.IsRangeTable(byref(s), getattr(lib,x))() ==0:
                min = lib.GetParamMin(byref(s), getattr(lib,x))[2]
                max = lib.GetParamMax(byref(s), getattr(lib,x))[2]
                parameters[x] = (min, max)
            elif lib.IsSparseTable(byref(s), getattr(lib,x))() ==0:
                table = (c_ulong *32)()
                r = lib.GetParamSparseTable(byref(s), getattr(lib,x), table, c_long(32))
                value = lib.GetParam(byref(s), getattr(lib,x))[2]
                parameters[x] = (list(r[2])[:r[3]])
    for x in lib('enums', 'QCam_ParamS32'):
        if lib.IsParamS32Supported(handle, getattr(lib, x))() == 0:
            if lib.IsRangeTableS32(byref(s), getattr(lib,x))() ==0:
                min = lib.GetParamS32Min(byref(s), getattr(lib,x))[2]
                max = lib.GetParamS32Max(byref(s), getattr(lib,x))[2]
                parameters[x] = (min, max)
            elif lib.IsSparseTableS32(byref(s), getattr(lib,x))() ==0:
                table = (c_ulong *32)()
                r = lib.GetParamSparseTableS32(byref(s), getattr(lib,x), table, c_long(32))
                parameters[x] = (list(r[2])[:r[3]])
    for x in lib('enums', 'QCam_Param64'):
        if lib.IsParam64Supported(handle, getattr(lib, x))() == 0:
            if lib.IsRangeTable64(byref(s), getattr(lib,x))() ==0:
                min = lib.GetParam64Min(byref(s), getattr(lib,x))[2]
                max = lib.GetParam64Max(byref(s), getattr(lib,x))[2]
                parameters[x] = (min, max)
            elif lib.IsSparseTable64(byref(s), getattr(lib,x))() ==0:
                table = (c_ulong *32)()
                r = lib.GetParamSparseTable64(byref(s), getattr(lib,x), table, c_long(32))
                parameters[x] = (list(r[2])[:r[3]])

def getParam(param):
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    if param in lib('enums', 'QCam_Param'):
        value = lib.GetParam(byref(s), getattr(lib, param))[2]
    elif param in lib('enums', 'QCam_ParamS32'):
        value = lib.SetParamS32(byref(s), getattr(lib, param))[2]
    elif param in lib('enums', 'QCam_Param64'):
        value = lib.SetParam64(byref(s), getattr(lib, param))[2]
    return value

def setParam(param, value):
    s = lib.ReadSettingsFromCam(handle)[1]
    if param in lib('enums', 'QCam_Param'):
        lib.SetParam(byref(s), getattr(lib, param), c_ulong(value))
    elif param in lib('enums', 'QCam_ParamS32'):
        lib.SetParamS32(byref(s), getattr(lib, param), c_long(value))
    elif param in lib('enums', 'QCam_Param64'):
        lib.SetParam64(byref(s), getattr(lib, param), c_ulonglong(value))
    lib.SendSettingsToCam(handle, byref(s))

def getParams(*params):
    s = lib.ReadSettingsFromCam(handle)[1]
    dict = {}
    for param in params:
        if param in lib('enums', 'QCam_Param'):
            value = lib.GetParam(byref(s), getattr(lib, param))[2]
        elif param in lib('enums', 'QCam_ParamS32'):
            value = lib.GetParamS32(byref(s), getattr(lib, param))[2]
        elif param in lib('enums', 'QCam_Param64'):
            value = lib.GetParam64(byref(s), getattr(lib, param))[2]
        dict[param]=value
    return dict

def setParams(**params):
    s = lib.ReadSettingsFromCam(handle)[1]
    for param in params:
        if param in lib('enums', 'QCam_Param'):
            lib.SetParam(byref(s), getattr(lib, param), c_ulong(params[param]))
        elif param in lib('enums', 'QCam_ParamS32'):
            lib.SetParamS32(byref(s), getattr(lib, param), c_long(params[param]))
        elif param in lib('enums', 'QCam_Param64'):
            lib.SetParam64(byref(s), getattr(lib, param), c_ulonglong(params[param]))
    lib.SendSettingsToCam(handle, byref(s))
    
loadDriver()
cameras = listCameras()
handle = openCamera(cameras[0])

#b = lib.SetStreaming(handle, 1)
#n = 0
#def fn(*args):
#    #global n
#    #n +=1
#    print "CALLBACK:", args
#    #f, a = mkFrame()
#    #print '1.1'
#    #lib.QueueFrame(handle, f, lib.AsyncCallback(fn), lib.qcCallbackDone, 0, n)
#    #print '1.2'
#f, a = mkFrame()
#
#qf = lib.QueueFrame(handle, f, lib.AsyncCallback(fn), lib.qcCallbackDone, 0, 0)
#print qf()
#print qf[1]

#app = QtGui.QApplication([])
