import time
from ctypes import *
import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))
from clibrary import *
from numpy import empty, uint16, ascontiguousarray
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

def call(function, *args):
    a = function(*args)
    if a() != 0:
        for x in lib('enums', 'QCam_Err'):
            if lib('enums', 'QCam_Err')[x] == a():
                raise Exception("There was an error running %s. Error code = %s" %(function, x)) ##how do I make this report the name of the function rather than it's type?
    else:
        return a
    
def quit():
    lib.CloseCamera(handle)
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
    frame = ascontiguousarray(empty((10, s/2), dtype=uint16))[5]
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
                except: ###Need to fix this so it only catches exceptions raised by call()
                    min = call(lib.GetParamMin, byref(s), getattr(lib,x))[2]
                    max = call(lib.GetParamMax, byref(s), getattr(lib,x))[2]
                    parameters[x] = (min, max)
            except:
                p = lib.GetParam(byref(s), getattr(lib, x))[2]
                parameters[x] = p
    for x in lib('enums', 'QCam_ParamS32'):
        if lib.GetParamS32(byref(s), getattr(lib, x))() == 0:
            try:
                table = (c_ulong *32)()
                r = call(lib.GetParamSparseTableS32, byref(s), getattr(lib,x), table, c_long(32))
                parameters[x] = (list(r[2])[:r[3]])
            except:
                min = call(lib.GetParamS32Min, byref(s), getattr(lib,x))[2]
                max = call(lib.GetParamS32Max, byref(s), getattr(lib,x))[2]
                parameters[x] = (min, max)
    for x in lib('enums', 'QCam_Param64'):
        if lib.GetParam64(byref(s), getattr(lib, x))() == 0:
            try:
                table = (c_ulong *32)()
                r = call(lib.GetParamSparseTable64, byref(s), getattr(lib,x), table, c_long(32))
                parameters[x] = (list(r[2])[:r[3]])
            except:
                min = call(lib.GetParam64Min, byref(s), getattr(lib,x))[2]
                max = call(lib.GetParam64Max, byref(s), getattr(lib,x))[2]
                parameters[x] = (min, max)
                
camerainfo = {}
def getCameraInfo():
    for x in lib('enums', 'QCam_Info'):
        try:
            a = call(lib.GetInfo, handle, getattr(lib, x))
            camerainfo[x] = a[2]
        except:
            print ("No info for: ", x)
            
            
    

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
    call(lib.SendSettingsToCam, handle, byref(s))

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
    call(lib.SendSettingsToCam, handle, byref(s))
    
loadDriver()
cameras = listCameras()
handle = openCamera(cameras[0])
#setParam(lib.qprmDoPostProcessing, 0)
#setParams(qprmExposure=10000)
##setParams(qprmExposureRed=0, qprmExposureBlue=0)
#setParams(qprmReadoutSpeed=lib.qcReadout20M)
#
#setParams(qprmTriggerType=lib.qcTriggerFreerun, qprmImageFormat=lib.qfmtMono16)



#getCameraInfo()
#print camerainfo


#b = lib.SetStreaming(handle, 1)
#n = 0
#def fn(*args):
#    #global n
#    #n +=1
#    print "CALLBACK:", args
#    print a.max(), a.min(), a.mean()
#    #f, a = mkFrame()
#    #print '1.1'
#    #lib.QueueFrame(handle, f, lib.AsyncCallback(fn), lib.qcCallbackDone, 0, n)
#    #print '1.2'
#f, a = mkFrame()
#
#print "Queue frame.."
#qf = lib.QueueFrame(handle, f, lib.AsyncCallback(fn), lib.qcCallbackDone, 0, 10)
#print "Frame queued."
##print qf()
##print qf[1]
#
#time.sleep(3.0)
#print "starting app.."
#app = QtGui.QApplication([])
#print "app started."
#print a.shape, (camerainfo['qinfCcdWidth'], camerainfo['qinfCcdHeight'])
#a.shape = (camerainfo['qinfCcdWidth'], camerainfo['qinfCcdHeight'])
#print "create window"
#imw1 = gw.ImageWindow(a)
#print "show window"
#imw1.show()
#
#print "Done."
#
#app.exec_()
