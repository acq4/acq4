
from ctypes import *
import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))
from clibrary import *
from numpy import *
from pyqtgraph import graphicsWindows as gw
from PyQt4 import QtGui
import atexit

def quit():
    lib.CloseCamera(handle)
atexit.register(quit)
    

p = CParser('QCamApi.h')

if sys.platform is 'darwin':
    dll = cdll.LoadLibrary('/Library/Frameworks/QCam.framework/QCam')
else:
    dll = windll.QCamDriver
    
lib = CLibrary(dll, p, prefix = 'QCam_')        #makes it so that functions in the header file can be accessed using lib.nameoffunction, ie: QCam_LoadDriver is lib.LoadDriver
                                                #also interprets all the typedefs for you....very handy
                                                #anything from the header needs to be accessed through lib.yourFunctionOrParameter


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
    
def grabFrame():
    s = lib.GetInfo(handle, lib.qinfImageSize)[2]
    f = lib.Frame()
    frame = empty(s, dtype=utype)
    f.pBuffer = frame.ctypes.data
    f.bufferSize = s
    lib.GrabFrame(handle, byref(f))
    w = lib.GetInfo(handle, qinfCcdWidth)[2]
    frame.shape(s/w, w)
    return frame

loadDriver()
cameras = listCameras()
handle = openCamera(cameras[0])
  
 
#s = lib.GetInfo(handle, lib.qinfImageSize)
#frame = lib.Frame()
#buffer = empty(s[2], dtype = ubyte)
#frame.pBuffer = buffer.ctypes.data
#frame.bufferSize = s[2]
#lib.GrabFrame(handle, byref(frame))


app = QtGui.QApplication([])
