from __future__ import print_function
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..\\..\\..\\'))

from . import pvcam
import atexit

def quit():
    global cam
    cam.close()
atexit.register(quit)


p = pvcam.PVCam
cams = p.listCameras()
print("\nCameras:", cams)

print("\ngetCamera...")
cam = p.getCamera(cams[0])
print("\nParameters:")
def listParams():
    params = cam.listParams()
    for p in params:
        v = str(cam.getParam(p))
        print(p, " "*(20-len(p)), v, " "*(30-len(v)), params[p])
listParams()
