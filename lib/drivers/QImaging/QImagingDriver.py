
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

def getParam(param):
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    return lib.GetParam(byref(s), param)[2]

### Make lists of the parameters available and current value of each parameter on the current camera.  
parameters = {}
def listParams():
    #take our value and type
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    for x in lib('enums', 'QCam_Param'): ##FIX this so that the name anonEnum16 is not hardwriten into the function!
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
    print 'done with params'
    for x in lib.anonEnum17.keys():
        print '1.0', x
        if lib.IsParamS32Supported(handle, getattr(lib, x))() == 0:
            print '1.1', x
            if lib.IsRangeTableS32(byref(s), getattr(lib,x))() ==0:
                print '1.2', x
                min = lib.GetParamS32Min(byref(s), getattr(lib,x))[2]
                print '1.3', x
                max = lib.GetParamS32Max(byref(s), getattr(lib,x))[2]
                print '1.4', x
                value = lib.GetParamS32(byref(s), getattr(lib,x))[2]
                parameters[x] = ((min, max), value, 'anonEnum17')
                print '1.5'
            elif lib.IsSparseTableS32(byref(s), getattr(lib,x))() ==0:
                print '1.6'
                table = (c_ulong *32)()
                print '1.7'
                r = lib.GetParamSparseTableS32(byref(s), getattr(lib,x), table, c_long(32))
                print '1.8'
                value = lib.GetParamS32(byref(s), getattr(lib,x))[2]
                parameters[x] = ((list(r[2])[:r[3]]), value, 'anonEnum17')
    print 'done with S32s'
    for x in lib.anonEnum18.keys():
        if lib.IsParam64Supported(handle, getattr(lib, x))() == 0:
            if lib.IsRangeTable64(byref(s), getattr(lib,x))() ==0:
                min = lib.GetParam64Min(byref(s), getattr(lib,x))[2]
                max = lib.GetParam64Max(byref(s), getattr(lib,x))[2]
                value = lib.GetParam64(byref(s), getattr(lib,x))[2]
                parameters[x] = ((min, max), value, 'anonEnum18')
            elif lib.IsSparseTable64(byref(s), getattr(lib,x))() ==0:
                table = (c_ulong *32)()
                r = lib.GetParamSparseTable64(byref(s), getattr(lib,x), table, c_long(32))
                value = lib.GetParam64(byref(s), getattr(lib,x))[2]
                parameters[x] = ((list(r[2])[:r[3]]), value, 'anonEnum18')
    print 'done with 64s'


def setParam(param, value):
    s = lib.ReadSettingsFromCam(handle)[1]
    if len(parameters.keys()) == 0:
        listParams()
    if param in lib('enums', 'QCam_Param'):
        lib.SetParam(byref(s), getattr(lib, param), c_ulong(value))
    elif parameters[param][1] == 'anonEnum17':
        lib.SetParamS32(byref(s), getattr(lib, param), c_long(value))
    elif parameters[param][1] == 'anonEnum18':
        lib.SetParam64(byref(s), getattr(lib, param), c_ulonglong(value))
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
