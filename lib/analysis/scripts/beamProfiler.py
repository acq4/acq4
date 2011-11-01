from PyQt4 import QtCore
import lib.Manager
import imageAnalysis

man = lib.Manager.getManager()
cam = man.getDevice('Camera')

frames = []

def collect(frame):
    global frames
    frames.append(frame)
    
cam.sigNewFrame.connect(collect)
    
def measure():
    if len(frames) == 0:
        QtCore.QTimer.singleShot(100, measure)
        return
    global frames
    frame = frames[-1]
    frames = []
    img = frame[0]
    w,h = img.shape
    img = img[2*w/5:3*w/5, 2*h/5:3*h/5]
    w,h = img.shape
    
    fit = imageAnalysis.fitGaussian2D(img, [100, w/2., h/2., w/4., 0])
    QtCore.QTimer.singleShot(2000, measure)
    print "WIDTH:", fit[0][3] * frame[1]['pixelSize'][0] * 1e6, "um"
    print " fit:", fit

measure()
