#!/usr/bin/python -i
import sys, os, re
from glob import glob
sys.path = ['libs', '/home/lcampagn/work/manis_lab/code/libs'] + sys.path

from helpers import *
from qtgraph.widgets import *
from qtgraph.graphicsWindows import *
from scipy.ndimage import *

if len(sys.argv) > 1:
  dataDir = sys.argv[1]
else:
  dataDir = dirDialog()
  #dataDir = '/home/lcampagn/work/manis_lab/data/2008.09.30/record_016'

info = {}
fd = open(os.path.join(dataDir, '.info'), 'r')
inf = re.sub('\r', '', fd.read())
fd.close()
exec(inf)

## Find file names
cFrames = glob(os.path.join(dataDir, '*.tif'))
dFrames = glob(os.path.join(dataDir, '*.dat'))
cFrames.sort()
dFrames.sort()

## Load images
img = loadImageList(cFrames).astype(float32)

## pre-processing
img = medianDivide(img, axis=0)

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
plotWindow = QtGui.QMainWindow()
plotCW = QtGui.QScrollArea()
plotWindow.setCentralWidget(plotCW)
plotVBox = QtGui.QVBoxLayout()
plotCW.setLayout(plotVBox)
plotWindow.show()
plotWindow.resize(600, 400)
plots = []


## Build analysis control window
ctrlWindow = QtGui.QMainWindow()
ctrlCW = QtGui.QWidget()
ctrlWindow.setCentralWidget(ctrlCW)
ctrlVBox = QtGui.QVBoxLayout()
ctrlCW.setLayout(ctrlVBox)
ctrlRadius = QtGui.QDoubleSpinBox()
ctrlRadius.setDecimals(1)
ctrlRadius.setSingleStep(0.5)
ctrlRadius.setRange(0.5, 1000.)
ctrlGenROI = QtGui.QPushButton("Generate ROIs")
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
  roi.setPen(QtGui.QPen(QtGui.QColor(*c)))
  rois.append(roi)
  images[0].scene.addItem(roi)
  p = PlotWidget()
  p.ui.btnHorizScale.setChecked(True)
  p.addPlot(ROIPlot(roi, img, images[0].imageItem, axes=(1,2), xVals=cTimes, color=c))
  plotVBox.addWidget(p)
  
  p.line = QtGui.QGraphicsLineItem(0, 1e100, 0, -1e100)
  p.scene.addItem(p.line)
  p.line.setPen(QtGui.QPen(QtGui.QColor(200, 200, 0)))
  QtCore.QObject.connect(images[0].ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), lambda i: p.line.setLine(cTimes[i], 1e100, cTimes[i], -1e100))
  QtCore.QObject.connect(images[0].ui.timeSlider, QtCore.SIGNAL('valueChanged(int)'), p.scene.invalidate)
  ## improves performance
  #images[0].ui.timeSlider.setTracking(False)
  
  QtCore.QObject.connect(p, QtCore.SIGNAL('closed'), lambda: images[0].scene.removeItem(roi))
  
  for pp in plots:
    p.view.lockXRange(pp.view)
    pp.view.lockXRange(p.view)
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
  img -= enhImage.imageItem.blackLevel
  img[img < 0] = 0.
  #showImg(img, title="Masked, thresholded image")
  
  labels = label(img)[0]
  
  for l in find_objects(labels):
    addROI()
    r = rois[-1]
    r.setPos([l[0].start-2, l[1].start-2])
    r.setSize([5, 5])
  plots[0].view.setXRange(QtCore.QRectF(0, 0, cTimes[-1], 1))
  
act = activeRegions(img)
arImg = showImg(act, title='active regions')

enhImage = showImg(zeros((2, 2)), "Active regions (enhanced)")
def updateEnhancedImage(r):
  global act, enhImage
  enh = enhanceCells(act, radius=r)
  enhImage.updateImage(enh, autoRange=True)
  #showImg(enh, title="Active region (Enhanced for cells)")



QtCore.QObject.connect(ctrlRadius, QtCore.SIGNAL('valueChanged(double)'), updateEnhancedImage)
ctrlRadius.setValue(3.0)

QtCore.QObject.connect(ctrlGenROI, QtCore.SIGNAL('clicked()'), buildROIs)

#l = labelPeaks(enh, threshold=0.4)
#lcImg = showImg(l, title='labeled cells')
  
#buildROIs(l)



