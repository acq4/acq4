import sys
sys.path.append('..\..\util')

import pvcam
import atexit

def quit():
    global cam
    cam.close()
atexit.register(quit)


p = pvcam.PVCam
cams = p.listCameras()
print "\nCameras:", cams

print "\ngetCamera..."
cam = p.getCamera(cams[0])
print "\nParameters:"
params = cam.listParams()
for p in params:
    print p, "\t", params[p]