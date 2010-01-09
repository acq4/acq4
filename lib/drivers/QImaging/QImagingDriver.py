
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
    print a(), a[1]
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

def getParamValue(param):
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    return lib.GetParam(byref(s), param)[2]

### Make lists of the parameters available on the current camera.  
param = {}
def listParams():
    s = lib.ReadSettingsFromCam(handle)[1]
    s.size = sizeof(s)
    for x in lib.anonEnum16.keys(): ##FIX this so that the name anonEnum16 is not hardwriten into the function!
        if lib.IsParamSupported(handle, getattr(lib, x))() == 0:
            if lib.IsRangeTable(byref(s), getattr(lib,x))() ==0:
                min = lib.GetParamMin(byref(s), getattr(lib,x))[2]
                max = lib.GetParamMax(byref(s), getattr(lib,x))[2]
                param[x] = (min, max)
            elif lib.IsSparseTable(byref(s), getattr(lib,x))() ==0:
                table = (c_ulong *32)()
                r = lib.GetParamSparseTable(byref(s), getattr(lib,x), table, c_long(32))
                param[x] = list(r[2])[:r[3]]
            
            
paramS32 = []
def listParamS32s():
    for x in lib.anonEnum17.keys():
        if lib.IsParamSupported(handle, getattr(lib, x))() == 0:
            paramS32.append(x)
param64 = []
def listParam64s():
    for x in lib.anonEnum18.keys():
        if lib.IsParamSupported(handle, getattr(lib, x))() == 0:
            param64.append(x)
def listAvailableParams():
    listParams()
    listParamS32s()
    listParam64s()
    return
##make function that sets a parameter - takes parameter as an argument
#    make a settings instance
#    read settings
#    use setparam - use if statement with all the different types of parameters to determine which setparam function to use
#    then send settings to cam

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
