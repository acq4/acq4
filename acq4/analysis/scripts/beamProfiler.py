from __future__ import print_function
from acq4.util import Qt
import acq4.Manager
import acq4.util.imageAnalysis as imageAnalysis

run = True
man = acq4.Manager.getManager()
cam = man.getDevice('Camera')

frames = []

def collect(frame):
    global frames
    frames.append(frame)
    
cam.sigNewFrame.connect(collect)
    
def measure():
    if len(frames) == 0:
        Qt.QTimer.singleShot(100, measure)
        return
    global run
    if run:
        global frames
        frame = frames[-1]
        frames = []
        img = frame.data()
        w,h = img.shape
        img = img[2*w/5:3*w/5, 2*h/5:3*h/5]
        w,h = img.shape
        
        fit = imageAnalysis.fitGaussian2D(img, [100, w/2., h/2., w/4., 0])
        # convert sigma to full width at 1/e
        fit[0][3] *= 2 * 2**0.5
        print("WIDTH:", fit[0][3] * frame.info()['pixelSize'][0] * 1e6, "um")
        print(" fit:", fit)
    else:
        global frames
        frames = []
    Qt.QTimer.singleShot(2000, measure)

measure()
