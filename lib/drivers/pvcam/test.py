import sys
sys.path.append('C:\\cygwin\\home\\Experimenters\\luke\\acq4\\lib\\util')

import pvcam
p = pvcam.PVCam
cams = p.listCameras()
print "cameras:", cams
cam = p.getCamera(cams[0])
