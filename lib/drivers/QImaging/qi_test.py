import time
from ctypes import *
import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))
from clibrary import *
from numpy import empty, uint16, ascontiguousarray, concatenate, newaxis
from pyqtgraph import graphicsWindows as gw
from PyQt4 import QtGui
from QImagingDriver import *
import atexit
p = CParser('QCamApi.h', cache='QCamApi.h.cache', macros={'_WIN32': '', '__int64': ('long long')})
if sys.platform == 'darwin':
    dll = cdll.LoadLibrary('/Library/Frameworks/QCam.framework/QCam')
else:
    dll = windll.QCamDriver
lib = CLibrary(dll, p, prefix = 'QCam_')        #makes it so that functions in the header file can be accessed using lib.nameoffunction, ie: QCam_LoadDriver is lib.LoadDriver
                                                #also interprets all the typedefs for you....very handy
                                                #anything from the header needs to be accessed through lib.yourFunctionOrParamete


###Load driver and camera
qcd = _QCamDriverClass()
cam = qcd.getCamera(qcd.listCameras()[0])

###Configure settings
cam.setParams(qprmReadoutSpeed='qcReadout20M', qprm64Exposure=100000000, qprmTriggerType='qcTriggerFreerun', qprmImageFormat='qtgtMono16')

    
#def quit():
#    lib.Abort(handle)
#    lib.SetStreaming(handle, 0)
#    lib.CloseCamera(handle)
#    lib.ReleaseDriver()
#    print 'Closing down...'
#atexit.register(quit)
#    
####Create callback function!
#def fn(*args):    
#    print "CALLBACK:", args
#
####Load driver and list cameras, and open camera
##print "LoadDriver: ", lib.LoadDriver()()
##number = c_ulong(10)
##L = lib.CamListItem * 10
##l = L()
##print "ListCameras: ", lib.ListCameras(l, number)()
##cameras = []
##for x in list(l)[:number.value]:
##cameras.append(x.cameraId)
##handle = lib.OpenCamera(cameras[0])[1]
#
#
#print "SetStreaming: ", lib.SetStreaming(handle, 1)()
#s = lib.ReadSettingsFromCam(handle)[1]
#s.size = sizeof(s)
#print "SetExposure: ", lib.SetParam64(byref(s), lib.qprm64Exposure, 100000000)()
#print "SetReadoutSpeed: ", lib.SetParam(byref(s), lib.qprmReadoutSpeed, lib.qcReadout20M )()
#print "SetTriggerType: ", lib.SetParam(byref(s), lib.qprmTriggerType, lib.qcTriggerFreerun)()
#print "SetImageFormat: ", lib.SetParam(byref(s), lib.qprmImageFormat, lib.qfmtMono16)() ###this line causes "Leaving callback loop!!!" message when SendSettings is called
#print "SendSettings: ", lib.SendSettingsToCam(handle, byref(s))()
#
#imsize = lib.GetInfo(handle, lib.qinfImageSize)[2]
#print 'image size: ', imsize
#
#frames = [lib.Frame()]*6
#arrays = []
#for i in range(len(frames)):
#    f = ascontiguousarray(empty(imsize/2, dtype=uint16))
#    frames[i].pBuffer = f.ctypes.data
#    frames[i].bufferSize = imsize
#    arrays.append(f)
#    
#for i in range(len(frames)):
#    print "Queuing frame: ", i  
#    a = lib.QueueFrame(handle, byref(frames[i]), lib.AsyncCallback(fn), lib.qcCallbackDone | lib.qcCallbackExposeDone, 0, i)
#    if a() == 0:
#        print "Queued frame: ", i
#        print a(), ':', a[0], ':', a[1], ':', a[2], ':', a[3], ':', a[4], ':', a[5]
#        time.sleep(1.0)
#    else:
#        print "Error queing frame:", i, 'error = ', a()
#        
#
#
#print "Done!"
