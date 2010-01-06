
from ctypes import *
from clibrary import *
p = CParser('QCamApi.h')
dll = cdll.LoadLibrary('/Library/Frameworks/QCam.framework/QCam')
dll = windll.QCamDriver
lib = CLibrary(dll, p, prefix = 'QCam_')        #makes it so that functions in the header file can be accessed using lib.nameoffunction, ie: QCam_LoadDriver is lib.LoadDriver
                                                #also interprets all the typedefs for you....very handy


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
        b.append(x.cameraID)
    return b
        

def openCamera(cameraID): #opens the camera and returns the handle
    """Opens the chosen camera and returns the handle. Takes cameraID parameter."""
    a = lib.OpenCamera(cameraID)
    if a() != 0:
        raise Exception('There was an error opening camera. Error code = ', a())
    return a[1] #possibly need to keep handle as a c type. use a.args[1] to do so
    
loadDriver()
cameras = listCameras
handle = openCamera(cameras[0])

    
 

