#!/usr/bin/python -i
# -*- coding: utf-8 -*-
from __future__ import print_function
import sys, os, re
from glob import glob
#sys.path = ['/home/lcampagn/work/manis_lab/code/libs'] + sys.path
localDir = os.path.dirname(__file__)
sys.path.append(os.path.join(localDir, '..'))
sys.path.append(os.path.join(localDir, '../util'))


#from helpers import *
from acq4.util import Qt
from acq4.pyqtgraph.widgets import *
from acq4.pyqtgraph.graphicsWindows import *
import Image
from acq4.util.functions import *
from scipy.ndimage import *
from scipy.ndimage import correlate

app = Qt.QApplication([])

def dirDialog(startDir='', title="Select Directory"):
  return str(Qt.QFileDialog.getExistingDirectory(None, title, startDir))
  
images = []
def showImg(data=None, parent=None, title='', copy=True):
    if data is None:
        fileName = fileDialog()
        title = fileName
        data = loadImg(fileName)
    elif isinstance(data, str):
        title = data
        data = loadImg(data)
    title = "Image %d: %s" % (len(images), title)
    i = ImageWindow(title=title)
    i.setImage(data)
    images.append(i)
    return i

def loadImageDir(dirName=None):
    if dirName is None:
        dirName = dirDialog()
        
    # Generate list of files, sort
    files = os.listdir(dirName)
    files.sort()
    files = [f for f in files if os.path.splitext(f)[1][1:] in IMAGE_EXTENSIONS]
    files = [os.path.join(dirName, f) for f in files]
    return loadImageList(files)

def loadImageList(files):
    # open first image to get dimensions
    img = asarray(Image.open(files[0]))
    
    # Create empty 3D array, fill first frame
    data = empty((len(files),) + img.shape, dtype=img.dtype)
    data[0] = img
    
    # Fill array with image data
    for i in range(1, len(files)):
        img = Image.open(files[i])
        data[i] = asarray(img)
        
    return data.transpose((0, 2, 1))

def loadImg(fileName=None):
    if fileName is None:
        fileName = fileDialog()
    if not os.path.isfile(fileName):
        raise Exception("No file named %s", fileName)
    img = Image.open(fileName)
    numFrames = 0
    try:
        while True:
            img.seek( numFrames )
            numFrames += 1
    except EOFError:
        img.seek( 0 )
        pass
    
    im1 = numpy.asarray(img)
    axes = range(0, im1.ndim)
    #print axes
    axes[0:2] = [1,0]
    axes = tuple(axes)
    #print axes
    im1 = im1.transpose(axes)

    if numFrames == 1:
        return im1
    
    imgArray = numpy.empty((numFrames,) + im1.shape, im1.dtype)
    frame = 0
    try:
        while True:
            img.seek( frame )
            imgArray[frame] = numpy.asarray(img).transpose(axes)
            frame += 1
    except EOFError:
        img.seek( 0 )
        pass
    return imgArray

def meanDivide(data, axis, inplace=False):
    if not inplace:
        d = empty(data.shape, dtype=float32)
    ind = [slice(None)] * data.ndim
    for i in range(0, data.shape[axis]):
        ind[axis] = i
        if inplace:
            data[tuple(ind)] /= data[tuple(ind)].mean()
        else:
            d[tuple(ind)] = data[tuple(ind)].astype(float32) / data[tuple(ind)].mean()
    if not inplace:
        return d






if len(sys.argv) > 1:
    dataDir = sys.argv[1]
else:
    dataDir = dirDialog()
    #dataDir = '/home/lcampagn/work/manis_lab/data/2008.09.30/record_016'

info = {}
try:
    fd = open(os.path.join(dataDir, '.info'), 'r')
    inf = re.sub('\r', '', fd.read())
    fd.close()
    exec(inf)
except:
    print("Warning: could not open info file")


## Find file names
cFrames = glob(os.path.join(dataDir, '*.tif'))
dFrames = glob(os.path.join(dataDir, '*.dat'))
cFrames.sort()
dFrames.sort()

## Load images
img = loadImageList(cFrames).astype(float32)

## pre-processing
#img = medianDivide(img, axis=0)

## Determine frame times
cTimes = []
dTimes = []
for f in cFrames:
    m = re.match(r'.*_([^_]+)\.tif', f)
    cTimes.append(float(m.groups()[0]))
for f in dFrames:
    m = re.match(r'.*_([^_]+)\.dat', f)
    dTimes.append(float(m.groups()[0]))
cTimes = array(cTimes)
dTimes = array(dTimes)
startTime = cTimes.min()
cTimes -= startTime
dTimes -= startTime

## Create image window
image = showImg(img)

## Build plot window
plotWindow = Qt.QMainWindow()
plotCW = Qt.QScrollArea()
plotWindow.setCentralWidget(plotCW)
plotSW = Qt.QWidget()
plotSW.setMinimumSize(300, 300)
plotSW.setSizePolicy(Qt.QSizePolicy(Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding))
plotCW.setWidget(plotSW)
plotCW.setWidgetResizable(True)
plotVBox = Qt.QVBoxLayout()
plotSW.setLayout(plotVBox)
plotWindow.show()
plotWindow.resize(600, 400)
plots = []


## Build analysis control window
ctrlWindow = Qt.QMainWindow()
ctrlCW = Qt.QWidget()
ctrlWindow.setCentralWidget(ctrlCW)
ctrlVBox = Qt.QVBoxLayout()
ctrlCW.setLayout(ctrlVBox)
ctrlRadius = Qt.QDoubleSpinBox()
ctrlRadius.setDecimals(1)
ctrlRadius.setSingleStep(0.5)
ctrlRadius.setRange(0.5, 1000.)
ctrlGenROI = Qt.QPushButton("Generate ROIs")
ctrlVBox.addWidget(ctrlRadius)
ctrlVBox.addWidget(ctrlGenROI)
ctrlWindow.show()


## Create physiology plot
if len(dFrames) > 0:
    physPlot = PlotWidget()
    plots.append(physPlot)
    plotVBox.addWidget(physPlot)


    ## Load physiology data
    physFrames = []
    for df in dFrames:
        d = fromfile(df, dtype=info['daq']['dtype'])
        d.shape = info['daq']['shape']
        physFrames.append(d)

    ## Decimate data, create times, and create plot
    dec = 0.1
    physData = zoom(hstack(physFrames), (1.0, dec))
    physTimes = linspace(0, physData.shape[1] / (info['daq']['rate'] * dec) + dTimes[0], physData.shape[1])
    physPlot.createPlot(physData[0], xVals=physTimes, color=(200, 200, 200))
    physPlot.autoRange()






## Function for adding new ROIs 
rois = []
def addROI():
    global rois, img, images, plots, cTimes, plotVBox
    c = intColor(len(rois))
    roi = RectROI([0, 0], [5, 5], translateSnap=True, scaleSnap=True)
    roi.setPen(Qt.QPen(c))
    rois.append(roi)
    images[0].addItem(roi)
    p = PlotWidget(None, name='ROI-%03d' % len(rois))
    #p.ui.btnHorizScale.setChecked(True)
    p.addCurve(ROIPlotItem(roi, img, images[0].imageItem, axes=(1,2), xVals=cTimes, color=c))
    p.setSizePolicy(Qt.QSizePolicy(Qt.QSizePolicy.MinimumExpanding, Qt.QSizePolicy.MinimumExpanding))
    p.setMinimumSize(100, 100)
    plotVBox.addWidget(p)
    
    
    p.line = Qt.QGraphicsLineItem(0, 1e100, 0, -1e100)
    p.addItem(p.line)
    p.line.setPen(Qt.QPen(Qt.QColor(200, 200, 0)))
    Qt.QObject.connect(images[0].cw, Qt.SIGNAL('timeChanged'), lambda i,t: p.line.setLine(cTimes[i], 1e100, cTimes[i], -1e100))
    #Qt.QObject.connect(images[0].cw, Qt.SIGNAL('timeChanged'), p.scene.invalidate)
    ## improves performance
    #images[0].ui.timeSlider.setTracking(False)
    
    Qt.QObject.connect(p, Qt.SIGNAL('closed'), lambda: images[0].removeItem(roi))
    
    #for pp in plots:
        #p.view.lockXRange(pp.view)
        #pp.view.lockXRange(p.view)
    plots.append(p)
    

def activeRegions(img):
    ## normalize first
    im1 = meanDivide(img, axis=0)
    im2 = im1.max(axis=0).astype(float32) - im1.min(axis=0)
    return im2 / gaussian_filter(im2, (15, 15))

def enhanceCells(img, radius=2.0):
    """Locate cells in image, return  image. Threshold should be between 0 and 1, where 1 is most selective."""
    
    ## Create a cell template
    c = generateSphere(radius)
    
    ## Create a 'center-surround' mask to enhance cell bodies
    im2 = img - (img.max()+img.min())*0.5
    c2 = c - c.max()*0.5
    print(im2.shape, c2.shape)
    mask = correlate(im2, c2)
    #showImg(mask, title='correlation mask')
    
    ## Apply mask to original data
    im3 = mask * (img-img.min())
    return im3

#def labelPeaks(img, threshold=0.5):
    ### Threshold enhanced image
    #img -= img.min() + (img.max()-img.min()) * threshold
    #img[img < 0] = 0.
    ##showImg(img, title="Masked, thresholded image")
    
    #l = label(img)[0]
    #return l

def buildROIs():
    global enhImage, plots, cTimes
    img = enhImage.data.copy()
    
    ## Threshold enhanced image
    img -= enhImage.blackLevel()
    img[img < 0] = 0.
    #showImg(img, title="Masked, thresholded image")
    
    labels = label(img)[0]
    
    for l in find_objects(labels):
        addROI()
        r = rois[-1]
        r.setPos([l[0].start-2, l[1].start-2])
        r.setSize([5, 5])
    plots[0].setXRange(0, cTimes[-1])

def export():
    data = empty((len(plots)+1, img.shape[0]))
    data[0] = cTimes
    roiData = []
    for i in range(len(plots)):
        data[i+1] = plots[i].plots[0].getRoiData()
        roiData.append([rois[i].pos().x(), rois[i].pos().y(), rois[i].boundingRect().height(), rois[i].boundingRect().width()])
    f = saveDialog()
    writeCsv(data.transpose(), f)
    fd = open(f + '.info', 'w')
    for rd in roiData:
        fd.write(' '.join(map(str, rd)) + '\n')
    fd.close()


act = activeRegions(img)
arImg = showImg(act, title='active regions')

enhImage = showImg(zeros((2, 2)), "Active regions (enhanced)")
def updateEnhancedImage(r):
    global act, enhImage
    enh = enhanceCells(act, radius=r)
    enhImage.setImage(enh, autoRange=True)
    enhImage.data = enh
    #showImg(enh, title="Active region (Enhanced for cells)")



Qt.QObject.connect(ctrlRadius, Qt.SIGNAL('valueChanged(double)'), updateEnhancedImage)
ctrlRadius.setValue(3.0)

Qt.QObject.connect(ctrlGenROI, Qt.SIGNAL('clicked()'), buildROIs)

#l = labelPeaks(enh, threshold=0.4)
#lcImg = showImg(l, title='labeled cells')
    
#buildROIs(l)



