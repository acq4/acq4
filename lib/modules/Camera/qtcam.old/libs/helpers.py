import numpy, Image
from qtgraph.graphicsWindows import *
from PyQt4 import QtCore, QtGui

import os, re, math, time, threading, types
from MetaArray import *
from scipy import *
from scipy.optimize import leastsq
from scipy.ndimage.filters import gaussian_filter, median_filter, maximum_filter, minimum_filter
from scipy.ndimage import zoom
from scipy.io.mio import loadmat
from scipy.signal import deconvolve

qapp = None
def mkQapp():
  global qapp
  if QtGui.QApplication.instance() is None:
    qapp = QtGui.QApplication([])

def dirDialog(startDir='', title="Select Directory"):
  mkQapp()
  return str(QtGui.QFileDialog.getExistingDirectory(None, title, startDir))

def fileDialog():
  mkQapp()
  return str(QtGui.QFileDialog.getOpenFileName())

def writeCsv(data, fileName):
  file = open(fileName, 'w')
  for row in range(0, data.shape[0]):
    stringVals = ["%f" % x for x in data[row]]
    file.write(",".join(stringVals) + "\n")
  file.close()

def readCsv(fileName):
  file = open(fileName)
  data = file.readlines()
  shape = (len(data), len(data[0].split(',')))
  arr = empty(shape, dtype=float)
  for row in range(0, shape[0]):
    arr[row] = array([float(x) for x in data[row].split(',')])
  return arr

IMAGE_EXTENSIONS = ['tif', 'jpg', 'gif', 'png']

def loadImageDir(dirName=None):
  if dirName is None:
    dirName = dirDialog()
    
  # Generate list of files, sort
  files = os.listdir(dirName)
  files.sort()
  files = filter(lambda f: os.path.splitext(f)[1][1:] in IMAGE_EXTENSIONS, files)
  files = [os.join(dirName, f) for f in files]
  return loadImageList(files)

def loadImageList(files):
  print files[0]
  # open first image to get dimensions
  img = asarray(Image.open(files[0]))
  print img.shape
  
  # Create empty 3D array, fill first frame
  data = empty((len(files),) + img.shape, dtype=img.dtype)
  data[0] = img
  
  # Fill array with image data
  for i in range(1, len(files)):
    img = Image.open(files[i])
    data[i] = asarray(img)
    
  print data.shape
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


images = []
def showImg(data=None, parent=None, title='', copy=True):
  mkQapp()
  if data is None:
    fileName = fileDialog()
    title = fileName
    data = loadImg(fileName)
  elif type(data) is types.StringType:
    title = data
    data = loadImg(data)
  title = "Image %d: %s" % (len(images), title)
  i = ImageWindow(data, parent, title, copy=copy)
  images.append(i)
  return i

plots = []
def showPlot(data, parent=None, title=''):
  mkQapp()
  title = "Plot %d: %s" % (len(plots), title)
  i = PlotWindow(data, parent, title)
  plots.append(i)
  return i



## the built in logspace function is pretty much useless.
def logSpace(start, stop, num):
  num = int(num)
  d = (stop / start) ** (1./num)
  return start * (d ** arange(0, num+1))


def alpha(t, tau):
  """Return the value of an alpha function at time t with width tau."""
  t = max(t, 0)
  return (t / tau) * math.exp(1.0 - (t / tau));

def alphas(t, tau, starts):
  tot = 0.0
  for s in starts:
    tot += alpha(t-s, tau)
  return tot

### TODO: replace with faster scipy filters
def smooth(data, it=1):
  data = data.view(ndarray)
  d = empty((len(data)), dtype=data.dtype)
  for i in range(0, len(data)):
    start = max(0, i-1)
    stop = min(i+1, len(data)-1)
    d[i] = mean(data[start:stop+1])
  if it > 1:
    return smooth(d, it-1)
  else:
    return d

def maxDenoise(data, it):
  return smooth(data, it).max()

def absMax(data):
  mv = 0.0
  for v in data:
    if abs(v) > abs(mv):
      mv = v
  return mv

# takes data in form of [[t1, y1], [t2, y2], ...]
def triggers(data, trig):
  """Return a list of places where data crosses trig
  Requires 2-column array:  array([[time...], [voltage...]])"""
  
  if data.ndim == 2:
    tVals = []
    for i in range(0, data.shape[1]-1):
      v1 = data[1, i]
      v2 = data[1, i+1]
      if v1 <= trig and v2 > trig:
        g1 = data[0,i]
        g2 = data[0,i+1]
        tVals.append(g1 + (g2-g1)*((0.5-v1)/(v2-v1)))
    return tVals
  elif data.ndim == 1:
    tVals = []
    for i in range(0, data.shape[0]-1):
      v1 = data[i]
      v2 = data[i+1]
      if v1 <= trig and v2 > trig:
        tVals.append(i)
    return tVals
    

def slidingOp(template, data, op):
  data = data.view(ndarray)
  template = template.view(ndarray)
  tlen = template.shape[0]
  length = data.shape[0] - tlen
  result = empty((length), dtype=float)
  for i in range(0, length):
    result[i] = op(template, data[i:i+tlen])
  return result


def rmsMatch(template, data, thresh=0.75, method=""):
  #data = data.view(ndarray)
  #template = template.view(ndarray)
  #tlen = template.shape[0]
  #length = data.shape[0] - tlen
  #devs = empty((length), dtype=float)
  
  #for i in range(0, length):
    #dif = template - data[i:i+tlen]
    #devs[i] = dif.std()
  
  devs = slidingOp(template, data, lambda t,d: (t-d).std())
  
  tstd = template.std()
  blocks = argwhere(devs < thresh * tstd)[:, 0]
  if len(blocks) == 0:
    return []
  inds = list(argwhere(blocks[1:] - blocks[:-1] > 1)[:,0] + 1)
  inds.insert(0, 0)
  return blocks[inds]


def fastRmsMatch(template, data, thresholds=[0.85, 0.75], scales=[0.2, 1.0], minTempLen=4):
  """Do multiple rounds of rmsMatch on scaled-down versions of the data set"""
  
  data = data.view(ndarray)
  template = template.view(ndarray)
  tlen = template.shape[0]
  
  inds = None
  inds2 = None
  lastScale = None
  
  for i in range(0, len(scales)):
    ## Decide on scale to use for this iteration
    t1len = max(minTempLen, int(scales[i]*tlen))
    scale = float(t1len)/float(tlen)
    
    ## scale down data sets
    if scale == 1.0:
      t1 = template
      data1 = data
    else:
      t1 = signal.signaltools.resample(template, t1len)
      data1 = signal.signaltools.resample(data, int(data.shape[0] * scale))
    
    ## find RMS matches
    if inds is None:
      inds = rmsMatch(t1, data1, thresholds[i])
    else:
      ix = ceil(scale/lastScale)
      inds = ((inds*scale) - ix).astype(int)
      span = 2*ix + t1len
      inds2 = []
      for ind in inds:
        d = data1[ind:ind+span]
        m = rmsMatch(t1, d, thresholds[i])
        for n in m:
          inds2.append(ind+n)
      inds = inds2
    lastScale = scale
    inds = (array(inds) / scale).round()
  return inds.astype(int)




## generates a command data structure from func with n points
def cmd(func, n, time):
  return [[i*(time/float(n-1)), func(i*(time/float(n-1)))] for i in range(0,n)]


def inpRes(data, v1Range, v2Range):
  r1 = filter(lambda r: r['Time'] > v1Range[0] and r['Time'] < v1Range[1], data)
  r2 = filter(lambda r: r['Time'] > v2Range[0] and r['Time'] < v2Range[1], data)
  v1 = mean([r['voltage'] for r in r1])
  v2 = min(smooth([r['voltage'] for r in r2], 10))
  c1 = mean([r['current'] for r in r1])
  c2 = mean([r['current'] for r in r2])
  return (v2-v1)/(c2-c1)


def findActionPots(data, lowLim=-20e-3, hiLim=0, maxDt=2e-3):
  """Returns a list of indexes of action potentials from a voltage trace
  Requires 2-column array:  array([[time...], [voltage...]])
  Defaults specify that an action potential is when the voltage trace crosses 
  from -20mV to 0mV in 2ms or less"""
  data = data.view(ndarray)
  lastLow = None
  ap = []
  for i in range(0, data.shape[1]):
    if data[1,i] < lowLim:
      lastLow = data[0,i]
    if data[1,i] > hiLim:
      if lastLow != None and data[0,i]-lastLow < maxDt:
        ap.append(i)
        lastLow = None
  return ap

def getSpikeTemplate(ivc, traces):
  """Returns the trace of the first spike in an IV protocol"""
  
  ## remove all negative currents
  posCurr = argwhere(ivc['current'] > 0.)[:, 0]
  ivc = ivc[:, posCurr]
  
  ## find threshold index
  ivd = ivc['max voltage'] - ivc['mean voltage']
  ivdd = ivd[1:] - ivd[:-1]
  thrIndex = argmax(ivdd) + 1 + posCurr[0]
  
  ## subtract spike trace from previous trace
  minlen = min(traces[thrIndex].shape[1], traces[thrIndex-1].shape[1])
  di = traces[thrIndex]['Inp0', :minlen] - traces[thrIndex-1]['Inp0', :minlen]
  
  ## locate tallest spike
  ind = argmax(di)
  maxval = di[ind]
  start = ind
  stop = ind
  while di[start] > maxval*0.5:
    start -= 1
  while di[stop] > maxval*0.5:
    stop += 1
  
  return traces[thrIndex][['Time', 'Inp0'], start:stop]
  
def fitSigmoid(xVals, yVals, guess=[1.0, 0.0]):
  fn = lambda v, x: 1.0 / (1.0 + exp(-v[0] * (x-v[1])))
  err = lambda v, x, y: fn(v, x)-y
  return leastsq(err, guess, args=(xVals, yVals))


STRNCMP_REGEX = re.compile(r'(-?\d+(\.\d*)?((e|E)-?\d+)?)')
def strncmp(a, b):
  """Compare strings based on the numerical values they represent (for sorting). Each string may have multiple numbers."""
  global STRNCMP_REGEX
  am = STRNCMP_REGEX.findall(a)
  bm = STRNCMP_REGEX.findall(b)
  if len(am) > 0 and len(bm) > 0:
    for i in range(0, len(am)):
      c = cmp(float(am[i][0]), float(bm[i][0]))
      if c != 0:
        return c
  return cmp(a, b)

def highPass(data, dims):
  return data - gaussian_filter(data, sigma=dims)

def lowPass(data, dims):
  gaussian_filter(data, sigma=dims)

def gaussDivide(data, sigma):
  return data.astype(float32) / gaussian_filter(data, sigma=sigma)
  
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

def medianDivide(data, axis, inplace=False):
  if not inplace:
    d = empty(data.shape, dtype=float32)
  ind = [slice(None)] * data.ndim
  for i in range(0, data.shape[axis]):
    ind[axis] = i
    if inplace:
      data[tuple(ind)] /= data[tuple(ind)].median()
    else:
      d[tuple(ind)] = data[tuple(ind)].astype(float32) / data[tuple(ind)].mean()
  if not inplace:
    return d

def blur(data, sigma):
  return gaussian_filter(data, sigma=sigma)


def findTriggers(data, spacing=None, highpass=True, devs=1.5):
  if highpass:
    d1 = data - median_filter(data, size=spacing)
  else:
    d1 = data
  stdev = d1.std() * devs
  ptrigs = (d1[1:] > stdev*devs) * (d1[:-1] <= stdev)
  ntrigs = (d1[1:] < -stdev*devs) * (d1[:-1] >= -stdev)
  return (argwhere(ptrigs)[:, 0], argwhere(ntrigs)[:, 0])

def triggerStack(data, triggers, axis=0, window=None):
  if window is None:
    dt = (triggers[1:] - triggers[:-1]).mean()
    window = [int(-0.5 * dt), int(0.5 * dt)]
  shape = list(data.shape)
  shape[axis] = window[1] - window[0]
  total = zeros((len(triggers),) + tuple(shape), dtype=data.dtype)
  readIndex = [slice(None)] * data.ndim
  writeIndex = [0] + ([slice(None)] * data.ndim)
  
  for i in triggers:
    rstart = i+window[0]
    rend = i+window[1]
    wstart = 0
    wend = shape[axis]
    if rend < 0 or rstart > data.shape[axis]:
      continue
    if rstart < 0:
      wstart = -rstart
      rstart = 0
    if rend > data.shape[axis]:
      wend = data.shape[axis] - rstart
      rend = data.shape[axis]
    readIndex[axis] = slice(rstart, rend)
    writeIndex[axis+1] = slice(wstart, wend)
    total[tuple(writeIndex)] += data[tuple(readIndex)]
    writeIndex[0] += 1
  return total

  
def generateSphere(radius):
  radius2 = radius**2
  w = int(radius*2 + 1)
  d = empty((w, w), dtype=float32)
  for x in range(0, w):
    for y in range(0, w):
      r2 = (x-radius)**2+(y-radius)**2
      if r2 > radius2:
        d[x,y] = 0.0
      else:
        d[x,y] = sqrt(radius2 - r2)
  return d

def make3Color(r=None, g=None, b=None):
  i = r
  if i is None:
    i = g
  if i is None:
    i = b
    
  img = zeros(i.shape + (3,), dtype=i.dtype)
  if r is not None:
    img[..., 2] = r
  if g is not None:
    img[..., 1] = g
  if b is not None:
    img[..., 0] = b
  return img


def analyzeImage(sizes=[2, 10, 10]):
  fileName = fileDialog()
  data = loadImg(fileName)
  i1 = showImg(data, title=fileName)
  
  #flat = gaussDivide(data, [0, sizes[1], sizes[2]])
  #i2 = showImg(flat, title=fileName + " (flattened)")
  
  norm = data / minimum_filter(data.astype(float32), footprint=ones((sizes[0]*10, 1, 1)))
  i3 = showImg(norm, title=fileName + " (normalized)")
  
  activity = blur(norm, [sizes[0]*0.5, sizes[1]*0.5, sizes[2]*0.5]).std(axis=0)
  i4 = showImg(activity, fileName + " (activity)")
  
  i1.trace()
  #i2.trace(i1)
  i3.trace()
  i4.trace(i1)
  
  
def loadMatlab(fileName=None):
  if fileName is None:
    fileName = fileDialog()
  d = loadmat(fileName)
  blocks = []
  dbs = [x for x in d.keys() if x[:3] == 'db_']
  dbs.sort(lambda a, b: cmp(a[3:], b[3:]))
  for db in dbs:
    df = d['df' + db[3:]]
    #rec = df.Record
    traces = []
    for t in d[db]:
      rec = [x for x in dir(t) if x[:2] == 'd_'][0]
      traces.append(getattr(t, rec).data.transpose())
    info = {}
    for k in dir(df):
      if k[0] != '_':
        v = getattr(df, k)
        if hasattr(v, 'v'):
          info[k] = v.v
        else:
          info[k] = v
    blocks.append((traces, info))
  return blocks

def imgDeconvolve(data, div):
  ## pad data past the end with the minimum value for each pixel
  data1 = empty((data.shape[0]+len(div),) + data.shape[1:])
  data1[:data.shape[0]] = data
  dmin = data.min(axis=0)
  dmin.shape = (1,) + dmin.shape
  data1[data.shape[0]:] = dmin
  
  ## determine shape of deconvolved image
  dec = deconvolve(data1[:, 0, 0], div)
  shape1 = (dec[0].shape[0], data.shape[1], data.shape[2])
  shape2 = (dec[1].shape[0], data.shape[1], data.shape[2])
  dec1 = empty(shape1)
  dec2 = empty(shape2)
  
  ## deconvolve
  for i in range(0, shape1[1]):
    for j in range(0, shape1[2]):
      dec = deconvolve(data1[:,i,j], div)
      dec1[:,i,j] = dec[0]
      dec2[:,i,j] = dec[1]
  return (dec1, dec2)

def xColumn(data, col):
  """Take a column out of a 2-D MetaArray and turn it into the axis values for axis 1. (Used for correcting older rtxi files)"""
  yCols = range(0, data.shape[0])
  yCols.remove(col)
  b = data[yCols].copy()
  b._info[1] = data.infoCopy()[0]['cols'][col]
  b._info[1]['values'] = data[col].view(ndarray)
  return b

def dirReport(dirName):
  """Turn a directory of MetaArray files into a series of CSV files. Files that appear to be part of a series are concatenated together"""
  files = os.listdir(dirName)
  for f in files:
    f = os.path.normpath(dirName + '/' + f)
    arr = MetaArray(file=f)
    arr.writeCsv(f+'.csv')

  
  ## First group files by name
  #numRegx = re.compile(r'(-?\d+(\.\d*)?((e|E)-?\d+)?)')
  #groups = {}
  #for f in files:
    #fn = numRegx.sub('', f)
    #if not groups.has_key(fn):
      #groups[fn] = []
    #groups[fn].append(os.path.normpath(dirName + '/' + f))
  
  ### Turn each group into a single MetaArray
  
  #for g in groups:
    #if len(g) == 1:
      #arr = MetaArray(file=g[0])
      #arr.writeCsv(g[0]+'.csv')
    #else:
      #d = []
      #vals = []
      #for f in g:
        #d.append(MetaArray(file=f))
        #vals.append(numRegx.findall(f))
      
def intColor(ind):
  x = (ind * 280) % (256*3)
  r = clip(255-abs(x), 0, 255) + clip(255-abs(x-768), 0, 255)
  g = clip(255-abs(x-256), 0, 255)
  b = clip(255-abs(x-512), 0, 255)
  return (r, g, b)
