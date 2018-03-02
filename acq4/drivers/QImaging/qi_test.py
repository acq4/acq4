from __future__ import print_function
import time

import sys, os
d = os.path.dirname(__file__)
sys.path.append(os.path.join(d, '../../util'))

from numpy import empty, uint16, ascontiguousarray, concatenate, newaxis
from acq4.pyqtgraph import graphicsWindows as gw
from acq4.util import Qt
from .QImagingDriver import *
import atexit



###Load driver and camera
qcd = QCamDriverClass()
cam = qcd.getCamera(qcd.listCameras()[0])

###Configure settings
#cam.setParams(qprmReadoutSpeed='qcReadout20M', qprm64Exposure=100000000, qprmTriggerType='qcTriggerFreerun', qprmImageFormat='qtgtMono16')

    
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
#time.sleep(1.0)
#s = cam.listParams()
#print s

struct = lib('structs', 'QCam_Settings')
s = struct()
dll.QCam_ReadSettingsFromCam(cam.handle, byref(s))
#time.sleep(1.0)
v = c_ulong()
dll.QCam_GetParam(byref(s), lib.qprmBinning, byref(v))
print(v.value)