from ROPingTemplate import Ui_MainWindow
from qtgraph.GraphicsView import *
from qtgraph.graphicsItems import *
from qtgraph.widgets import *
from PyQt4 import QtGui, QtCore
import scipy, scipy.ndimage, scipy.signal
import sys
if '--mock' in sys.argv:
  sys.path = ['mock'] + sys.path
import nidaq, helpers

class ROPWindow(QtGui.QMainWindow):
  def __init__(self, mw):
    self.mw = mw
    QtGui.QMainWindow.__init__(self)
    self.ui = Ui_MainWindow()
    self.ui.setupUi(self)
    
    
    l1 = QtGui.QVBoxLayout(self.ui.imageWidget)
    l1.setMargin(0)
    self.imageView = GraphicsView(self.ui.imageWidget)
    l1.addWidget(self.imageView)
    self.imageScene = QtGui.QGraphicsScene(self)
    self.imageView.setScene(self.imageScene)
    self.imageView.setAspectLocked(True)
    self.imageView.invertY()
    self.imageItem = ImageItem()
    self.imageScene.addItem(self.imageItem)
    self.roi = RectROI([0, 0], [6, 6], centered=True)
    self.imageScene.addItem(self.roi)
    
    l2 = QtGui.QVBoxLayout(self.ui.plotWidget)
    l2.setMargin(0)
    self.plotView = GraphicsView(self.ui.plotWidget)
    l2.addWidget(self.plotView)
    self.plotScene = QtGui.QGraphicsScene(self)
    self.plotScene.addItem(Grid(self.plotView))
    self.plotView.setScene(self.plotScene)
    self.plotData = []
    self.plotGroup = QtGui.QGraphicsItemGroup()
    self.plotScene.addItem(self.plotGroup)
    self.plotView.setRange(QtCore.QRectF(-2.2, -90e-3, 2.4, 120e-3))
    self.plotTimer = QtCore.QTimer()
    QtCore.QObject.connect(self.plotTimer, QtCore.SIGNAL('timeout()'), self.updatePlotPos)
    
    
    self.daq = nidaq.NIDAQ
    aiChans = []
    devNames = self.daq.listDevices()
    for dName in devNames:
      dev = self.daq.getDevice(dName)
      aiChans.extend(dev.listAIChannels())
    self.ui.listCameraChannel.addItems(aiChans)
    self.ui.listCellChannel.addItems(aiChans)
    
    self.acquireThread = AcquireThread(self)
    self.analysisThread = AnalysisThread(self)
    
    self.cellChannel = self.cameraChannel = None
    self.setCameraChannel(0)
    self.setCellChannel(3)
    self.setSampleRate(20000.)
    self.setInputScale(1.0)
    
    self.frameBufferLength = 120
    self.frameBufferPtr = 0
    self.frameBufferWrap = False
    self.frameBuffer = None
    self.frameTimes = None
    self.imagePlot = None
    
    QtCore.QObject.connect(self.ui.btnAcquire, QtCore.SIGNAL('clicked()'), self.toggleAcquire)
    QtCore.QObject.connect(self.analysisThread, QtCore.SIGNAL('drawPlot'), self.updatePlot)
    QtCore.QObject.connect(self.mw.acquireThread, QtCore.SIGNAL('newFrame'), self.newFrame)
    QtCore.QObject.connect(self.analysisThread, QtCore.SIGNAL('newFrame'), self.markFrame)
    QtCore.QObject.connect(self.analysisThread, QtCore.SIGNAL('newImages'), self.updateImages)
    QtCore.QObject.connect(self.ui.listCameraChannel, QtCore.SIGNAL('currentIndexChanged(int)'), self.setCameraChannel)
    QtCore.QObject.connect(self.ui.listCellChannel, QtCore.SIGNAL('currentIndexChanged(int)'), self.setCellChannel)
    QtCore.QObject.connect(self.ui.spinSampleRate, QtCore.SIGNAL('valueChanged(double)'), self.setSampleRate)
    QtCore.QObject.connect(self.ui.spinInputScale, QtCore.SIGNAL('valueChanged(double)'), self.setInputScale)
    QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('showMessage'), self.showMessage)
    QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('finished()'), self.acqThreadStopped)

  def setPlotScroll(self, b):
    if b:
      self.plotTimer.start(100)
    else:
      self.plotTimer.stop()
      
  def newFrame(self, frame):
    (frame, info) = frame
    if self.frameBuffer is None or self.frameBuffer.shape[1:] != frame.shape:
      self.frameBuffer = empty((self.frameBufferLength,) + frame.shape, dtype=frame.dtype)
      self.frameTimes = empty((self.frameBufferLength,), dtype=float)
      self.frameBufferPtr = 0
      self.frameBufferWrap = False
    self.frameBuffer[self.frameBufferPtr] = frame
    self.frameTimes[self.frameBufferPtr] = info['time']
    self.frameBufferPtr += 1
    if self.frameBufferPtr >= self.frameBufferLength:
      self.frameBufferPtr = 0
      self.frameBufferWrap = True
      
  def toggleAcquire(self):
    if self.ui.btnAcquire.isChecked():
      self.acquireThread.start()
      self.analysisThread.start()
      self.setPlotScroll(True)
    else:
      #self.toggleRecord(False)
      self.acquireThread.stop()
      self.analysisThread.stop()
      self.setPlotScroll(False)
  
  def setSampleRate(self, rate):
    self.sampleRate = rate
    self.ui.spinSampleRate.setValue(rate)
  
  def setInputScale(self, scl):
    self.inputScale = scl
    self.ui.spinInputScale.setValue(scl)
  
  def setCameraChannel(self, ind):
    self.cameraChannel = str(self.ui.listCameraChannel.itemText(ind))
    self.ui.listCameraChannel.setCurrentIndex(ind)
    if self.cellChannel == self.cameraChannel:
      self.cameraChannel = None
    else:
      self.acquireThread.reset()
      
  def setCellChannel(self, ind):
    self.cellChannel = str(self.ui.listCellChannel.itemText(ind))
    self.ui.listCellChannel.setCurrentIndex(ind)
    if self.cellChannel == self.cameraChannel:
      self.cellChannel = None
    else:
      self.acquireThread.reset()

  def showMessage(self, msg):
    self.ui.statusbar.showMessage(msg)

  def acqThreadStopped(self):
    #self.toggleRecord(False)
    print "Acq thread stopped; stopping analysis thread"
    self.analysisThread.stop()
    self.setPlotScroll(False)
    self.ui.btnAcquire.setChecked(False)
    self.ui.btnAcquire.setEnabled(True)

  
  def stop(self):
    self.acquireThread.stop()
    self.hide()
  
  def updatePlotPos(self):
    self.plotGroup.setPos(-time.time(), 0.0)
    
    ## draw camera trace
    rect = self.roi.sceneBoundingRect()
    sx = int(rect.x())
    sy = int(rect.y())
    ex = int(sx + rect.width())
    ey = int(sy + rect.height())
    if ex == sx or ey == sy:
      return
    
    
    if self.frameBufferWrap:
      data = empty((2, self.frameBufferLength), dtype=float)
      p2 = self.frameBufferLength - self.frameBufferPtr
      data[0, :p2] = (self.frameBuffer[self.frameBufferPtr:, sx:ex, sy:ey]).astype(float).mean(axis=2).mean(axis=1)
      data[0, p2:] = (self.frameBuffer[:self.frameBufferPtr, sx:ex, sy:ey]).astype(float).mean(axis=2).mean(axis=1)
      data[1, :p2] = self.frameTimes[self.frameBufferPtr:]
      data[1, p2:] = self.frameTimes[:self.frameBufferPtr]
    else:
      data = empty((2, self.frameBufferPtr), dtype=float)
      data[0] = (self.frameBuffer[0:self.frameBufferPtr, sx:ex, sy:ey]).astype(float).mean(axis=2).mean(axis=1)
      data[1] = self.frameTimes[0:self.frameBufferPtr]
      
    data[0] -= median(data[0])
    data[0] *= 0.005
    data[1] -= data[1, -1]
    
    
    if self.imagePlot is not None:
      self.plotScene.removeItem(self.imagePlot)
    self.imagePlot = Plot(data[0], xvals=data[1], color=1)
    self.plotScene.addItem(self.imagePlot)
    #self.imagePlot.moveBy(-data[1, -1], 0.)
    
  
  def markFrame(self, frame):
    fTime = frame[1]['time']
    l = QtGui.QGraphicsEllipseItem(0, 0, 1e-3, 1e-3)
    self.plotGroup.addToGroup(l)
    l.setPen(QtGui.QPen(QtGui.QColor(100, 100, 100)))
    l.setPos(fTime, frame[0][120:130, 13:23].mean() * 1e-3 - 0.4)
    self.plotData.append({'info': frame[1], 'data': frame[0]})
    self.plotData[-1]['items'] = [l] 
  
  def updatePlot(self, data):
    self.plotData.append(data)
    now = time.time()
    
    ## draw new items
    items = []
    items.append(Plot(self.plotData[-1]['data']))
    items[-1].scale(data['info']['scale'], 1.0)
    self.plotGroup.addToGroup(items[-1])
    items[-1].setPos(data['info']['time'], 0.0)
    
    for tr in data['exTrigs']:
      items.append(QtGui.QGraphicsLineItem(0, -5e-3, 0, -15e-3))
      self.plotGroup.addToGroup(items[-1])
      items[-1].setPen(QtGui.QPen(QtGui.QColor(50, 200, 50)))
      items[-1].setPos(tr, 0.0)
    for tr in data['inTrigs']:
      items.append(QtGui.QGraphicsLineItem(0, -5e-3, 0, -15e-3))
      self.plotGroup.addToGroup(items[-1])
      items[-1].setPen(QtGui.QPen(QtGui.QColor(50, 50, 200)))
      items[-1].setPos(tr, 0.0)
    #for tr in data['exFrames']:
      #items.append(QtGui.QGraphicsLineItem(0, -15e-3, 0, -25e-3))
      #self.plotGroup.addToGroup(items[-1])
      #items[-1].setPen(QtGui.QPen(QtGui.QColor(50, 200, 50)))
      #items[-1].setPos(tr, 0.0)
    #for tr in data['inFrames']:
      #items.append(QtGui.QGraphicsLineItem(0, -15e-3, 0, -25e-3))
      #self.plotGroup.addToGroup(items[-1])
      #items[-1].setPen(QtGui.QPen(QtGui.QColor(50, 50, 200)))
      #items[-1].setPos(tr, 0.0)
    
    self.plotData[-1]['items'] = items
    #self.plotGroup.setPos(-now, 0.0)
    
    ## Remove old plot items
    while self.plotData[0]['info']['time'] < now - 5.0:
      for i in self.plotData[0]['items']:
        self.plotGroup.removeFromGroup(i)
        self.plotScene.removeItem(i)
      self.plotData.pop(0)
    
  def updateImages(self, data):
    if data['ex'] is not None:
      shape = data['ex'].shape + (3,)
      dtype = data['ex'].dtype
    elif data['in'] is not None:
      shape = data['in'].shape + (3,)
      dtype = data['in'].dtype
    elif data['bg'] is not None:
      shape = data['bg'].shape + (3,)
      dtype = data['bg'].dtype
    else:
      return
      
    img = zeros(shape, dtype)
    if data['ex'] is not None:
      img[..., 1] = scipy.ndimage.gaussian_filter((data['ex'] - data['ex'].min()).astype(dtype) / (float(data['ex'].max()) - float(data['ex'].min())), (2, 2))
    if data['in'] is not None:
      img[..., 0] = scipy.ndimage.gaussian_filter((data['in'] - data['in'].min()).astype(dtype) / (float(data['in'].max()) - float(data['in'].min())), (2, 2))
    if data['bg'] is not None:
      bg = 0.5 * (data['bg'] - data['bg'].min()).astype(dtype) / (float(data['bg'].max()) - float(data['bg'].min()))
      img[..., 2] += bg
      #img[..., 1] += bg
      #img[..., 2] += bg
    
    self.imageItem.updateImage(img, white=img.max(), black=img.min())
    #self.imageItem.setLevels()
    
    
class AcquireThread(QtCore.QThread):
  def __init__(self, mw):
    QtCore.QThread.__init__(self)
    self.mw = mw
    self.stopThread = False
    self.lock = QtCore.QMutex()
    #self.bufLock = QtCore.QMutex()
    self.info = None
    self.frameId = 0
    self.ringSize = 20
    self.frameSize = 4000
  
  #def getFrame(self, frame):
    ##print "acq.getFrame", frame
    #l = QtCore.QMutexLocker(self.bufLock)
    #if self.acqBuffer.has_key(frame):
      #return self.acqBuffer[frame]
    #else:
      #raise Exception("Requested frame %d is unavailable!" % frame)
        
  def run(self):
    print "starting acq thread.."
    rate = self.mw.sampleRate
    frameSize = self.frameSize
    camCh = self.mw.cameraChannel
    cellCh = self.mw.cellChannel
    #self.acqBuffer = {}
    lastFrame = None
    lastFrameTime = None
    self.lock.lock()
    self.stopThread = False
    self.lock.unlock()
    self.fps = None
    
    daqTask = None
    try:
      
      dev = self.mw.daq.getDevice(camCh.split('/')[0])
      daqTask = dev.createTask()
      daqTask.CreateAIVoltageChan(camCh, 'camera', nidaq.Val_RSE, -10., 10., nidaq.Val_Volts, None)
      daqTask.CreateAIVoltageChan(cellCh, 'cell', nidaq.Val_NRSE, -10., 10., nidaq.Val_Volts, None)
      daqTask.CfgSampClkTiming(None, rate, nidaq.Val_Rising, nidaq.Val_ContSamps, frameSize * 10)
      daqTask.start()
      while True:
        
        (data, samplesRead) = daqTask.read(frameSize)
        now = time.time()
        samplesAvailable = daqTask.GetReadAvailSampPerChan()
        info = {'time': now - (frameSize + samplesAvailable) / rate, 'rate': rate}
        #print "New DAQ frame timestamped %f" % info['time']
        if samplesAvailable > self.ringSize * frameSize * 0.5:
          self.showMessage("Warning: Daq acquisition falling behind")
        
        #self.bufLock.lock()
        #self.acqBuffer[self.frameId] = (data, info)
        #if self.acqBuffer.has_key(self.frameId-self.ringSize):
          #del self.acqBuffer[self.frameId-self.ringSize]
        #self.bufLock.unlock()
        
        self.emit(QtCore.SIGNAL("newFrame"), (data, info))
        self.frameId += 1
        
        self.lock.lock()
        if self.stopThread:
          self.lock.unlock()
          break
        self.lock.unlock()
        
      daqTask.stop()
    except:
      try:
        if daqTask is not None:
          daqTask.stop()
      except:
        pass
      #self.bufLock.unlock()
      raise
      self.emit(QtCore.SIGNAL("showMessage"), "ERROR Starting acquisition: %s %s" % (str(sys.exc_info()[1]), str(sys.exc_info()[0])))
    
  def stop(self):
    l = QtCore.QMutexLocker(self.lock)
    self.stopThread = True

  def reset(self):
    if self.isRunning():
      self.stop()
      self.wait()
      self.start()

  def showMessage(self, msg):
    self.emit(QtCore.SIGNAL('showMessage'), msg)

class AnalysisThread(QtCore.QThread):
  def __init__(self, mw):
    self.bufferTime = 5.0
    self.daqSpacing = 40
    self.mw = mw
    self.newDaqFrames = []
    self.newCamFrames = []
    self.camFrames = []
    self.daqFrames = []
    self.camLock = QtCore.QMutex()
    self.daqLock = QtCore.QMutex()
    self.lock = QtCore.QMutex()
    self.stopThread = False
    QtCore.QThread.__init__(self)
    QtCore.QObject.connect(self.mw.acquireThread, QtCore.SIGNAL('newFrame'), self.newDaqFrame)
    QtCore.QObject.connect(self.mw.mw.acquireThread, QtCore.SIGNAL('newFrame'), self.newCamFrame)
    
    
  def newDaqFrame(self, fid):
    if self.isRunning():
      dlock = QtCore.QMutexLocker(self.daqLock)
      self.newDaqFrames.append(fid)
    
  def newCamFrame(self, frame):
    if self.isRunning():
      cLock = QtCore.QMutexLocker(self.camLock)
      self.newCamFrames.append(frame)
    
  def generateTemplate(self):
    tau = self.mw.ui.spinPspTau.value() * 1e-3
    size = tau * 10 * self.sampleRate / self.downsample
    self.template = empty((size,), dtype=float)
    dt = 1.0 * self.downsample / self.sampleRate
    for i in range(0, int(size)):
      self.template[i] = helpers.alpha(i*dt, tau)
    
  def run(self):
    self.downsample = self.mw.ui.spinDownsample.value()
    self.inputScale = self.mw.ui.spinInputScale.value()
    self.stdevs = self.mw.ui.spinPspTolerance.value()
    self.sampleRate = self.mw.sampleRate
    self.generateTemplate()
    self.exImage = None
    self.inImage = None
    self.bufferTime = 3.0
    self.stopThread = False
    self.newDaqframes = []
    self.newCamFrames = []
    while True:
      
      dlock = QtCore.QMutexLocker(self.daqLock)
      handleDaqFrames = self.newDaqFrames[:]
      self.newDaqFrames = []
      del dlock
      
      cLock = QtCore.QMutexLocker(self.camLock)
      handleCamFrames = self.newCamFrames[:]
      self.newCamFrames = []
      del cLock
      
      while len(handleDaqFrames) > 0:
        self.handleDaqFrame(handleDaqFrames.pop(0))
      
      while len(handleCamFrames) > 0:
        self.handleCamFrame(handleCamFrames.pop(0))
      
      time.sleep(10e-6)
      
      l = QtCore.QMutexLocker(self.lock)
      if self.stopThread:
        break
      del l
    
  def handleCamFrame(self, frame):
    self.camFrames.append(frame)
    now = time.time()
    while len(self.camFrames) > 0 and self.camFrames[0][1]['time'] < now - self.bufferTime:
      self.camFrames.pop(0)
    
    frameIntervals = []
    if len(self.camFrames) > 1:
      for i in range(1, len(self.camFrames)):
        frameIntervals.append(self.camFrames[i][1]['time'] - self.camFrames[i-1][1]['time'])
      self.framerate = 1.0 / median(frameIntervals)
  
  def handleDaqFrame(self, frame):
    camInd = 0
    cellInd = 1
    (frame, info) = frame
    frame = scipy.ndimage.zoom(frame, (1.0, 1.0 / self.downsample))
    info['scale'] = self.downsample / self.sampleRate
    frame[cellInd] *= self.inputScale
    
    self.daqFrames.append((frame, info))
    now = time.time()
    while len(self.daqFrames) > 0 and self.daqFrames[0][1]['time'] < now - self.bufferTime:
      self.daqFrames.pop(0)
    
    
    ## do template match, package hit times with frame
    med = median(frame[cellInd])
    deconv = scipy.signal.deconvolve(frame[cellInd]-med, self.template)[0][1:]
    (exTrigs, inTrigs) = helpers.findTriggers(deconv, spacing=self.daqSpacing, devs=self.stdevs)
    exTrigs = map(lambda x: info['time'] + x * self.downsample / self.sampleRate, exTrigs)
    inTrigs = map(lambda x: info['time'] + x * self.downsample / self.sampleRate, inTrigs)
    #print exTrigs, inTrigs
    
    ## Add deconvolved data to display list
    #shd = zeros((1, frame.shape[1]), dtype=float)
    #shd[0, 1:1+deconv.shape[0]] = deconv
    #frame = concatenate([frame, shd])
    #frame[2, 0:self.template.shape[0]] += self.template*20.
    
    #drawData = frame
    drawData = frame[cellInd]
    
    ## locate camera triggers
    #camTrigs = helpers.triggers(frame[camInd], 0.5)
    cam1 = frame[camInd, :-1]
    cam2 = frame[camInd, 1:]
    camOnTrigs = list(argwhere((cam1 < 0.5) * (cam2 >= 0.5))[:, 0])
    camOffTrigs = list(argwhere((cam1 >= 0.5) * (cam2 < 0.5))[:, 0])
    if len(camOnTrigs) > 0 and len(camOffTrigs) > 0:
      
      ## close up triggers if needed
      if camOnTrigs[0] > camOffTrigs[0]:
        camOnTrigs.insert(0, 0)
      if camOnTrigs[-1] > camOffTrigs[-1]:
        camOffTrigs.append(frame.shape[1])
    
    ## at this point, the camera on/off triggers should match up by index.
    ## Convert to times
    camOnTrigs = map(lambda x: info['time'] + x * self.downsample / self.sampleRate, camOnTrigs)
    camOffTrigs = map(lambda x: info['time'] + x * self.downsample / self.sampleRate, camOffTrigs)
    
    ## Convert triggers to frame times
    exFrameTimes = []
    inFrameTimes = []
    
    for tr in exTrigs:
      for i in range(0, len(camOnTrigs)):
        if camOffTrigs[i] > tr:
          exFrameTimes.append(camOnTrigs[i])
          break
    for tr in inTrigs:
      for i in range(0, len(camOnTrigs)):
        if camOffTrigs[i] > tr:
          inFrameTimes.append(camOnTrigs[i])
          break
    exFrameTimes = set(exFrameTimes)
    inFrameTimes = set(inFrameTimes)
    
    ## Bundle up plot data and send back to GUI thread
    #drawData[camInd] *= 0.01
    plotData = {'data': drawData, 'info': info, 'inTrigs': inTrigs, 'exTrigs': exTrigs, 'inFrames': inFrameTimes, 'exFrames': exFrameTimes}
    self.emit(QtCore.SIGNAL('drawPlot'), plotData)
    
    
    ## Match frame times with real frames
    exFrames = self.findCamFrames(exFrameTimes)
    inFrames = self.findCamFrames(inFrameTimes)
    #print "Have %d camera frames" % len(self.camFrames)
    #print exFrames
    #print inFrames
    
    inAvg = None
    exAvg = None
    
    mixRate = 0.95
    exStack1 = None
    exStack2 = None
    if len(exFrames) > 0:
      ## background-subtract and average together frames
      exStack1 = empty( (len(exFrames),) + self.camFrames[exFrames[0]][0].shape, dtype=self.camFrames[exFrames[0]][0].dtype)
      exStack2 = empty( (len(exFrames),) + self.camFrames[exFrames[0]][0].shape, dtype=self.camFrames[exFrames[0]][0].dtype)
      for i in range(0, len(exFrames)):
        exStack1[i] = self.camFrames[exFrames[i]][0]
        exStack2[i] = self.camFrames[exFrames[i]-1][0]
      exAvg = (exStack2-exStack1).astype(float32).mean(axis=0)
      
      ## Mix new frames into old
      if self.exImage is None:
        self.exImage = exAvg
      else:
        mix = mixRate ** len(exFrames)
        self.exImage *= mixRate
        self.exImage += (1.0-mixRate) * exAvg
    
    
    if len(inFrames) > 0:
      ## background-subtract and average together frames
      inStack1 = empty( (len(inFrames),) + self.camFrames[inFrames[0]][0].shape, dtype=self.camFrames[inFrames[0]][0].dtype)
      inStack2 = empty( (len(inFrames),) + self.camFrames[inFrames[0]][0].shape, dtype=self.camFrames[inFrames[0]][0].dtype)
      for i in range(0, len(inFrames)):
        inStack1[i] = self.camFrames[inFrames[i]][0]
        inStack2[i] = self.camFrames[inFrames[i]-1][0]
      inAvg = (inStack2-inStack1).astype(float32).mean(axis=0)
      
      ## Mix new frames into old
      if self.inImage is None:
        self.inImage = inAvg
      else:
        mix = mixRate ** len(inFrames)
        self.inImage *= mixRate
        self.inImage += (1.0-mixRate) * inAvg
    
    ## Send new images to GUI thread
    bg = None
    if len(self.camFrames) > 0:
      bg = self.camFrames[-1][0]
    self.emit(QtCore.SIGNAL('newImages'), {'in': self.inImage, 'ex': self.exImage, 'bg': bg})
    #if exStack1 is not None:
      #self.emit(QtCore.SIGNAL('newImages'), {'in': exStack1.mean(axis=0), 'ex': exStack2.mean(axis=0)})
    
  
  def findCamFrames(self, times):
    frames = []
    for t in times:
      minTime = None
      minFrame = None
      for i in range(0, len(self.camFrames)):
        dt = abs(t - self.camFrames[i][1]['time'])
        if minTime is None or dt < minTime:
          minTime = dt
          minFrame = i
      if minFrame < 1:
        pass
        #print "Best frame already discarded"
      elif minFrame >= len(self.camFrames):
        pass
        #print "Frame is not yet available"
      elif minTime > 0.5/self.framerate:
        pass
        #print "Can't match frame!"
      elif minFrame not in frames:
        frames.append(minFrame)
    return frames
  
  
  def showMessage(self, msg):
    self.emit(QtCore.SIGNAL('showMessage'), msg)

  def stop(self):
    l = QtCore.QMutexLocker(self.lock)
    self.stopThread = True
