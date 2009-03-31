import scipy.ndimage, numpy, time, os, mockdata


class MyMockPVCam:
  def __init__(self):
    pass
  def listCameras(self):
    return ['mock']
  def getCamera(self, choice):
    return Camera()

PVCam = MyMockPVCam()

class Camera:
  def __init__(self):
    self.data = mockdata.getMockData('cam')
    ## Draw up-arrow in top-left fo every frame
    #self.data[:, 5, 5:10] = 0
    #self.data[:, 4:7, 6] = 0
    #self.data[:, 3:8, 7] = 0
    self.frameRate = 25
    self.loopTime = 20.
    self.currentBufferFrame = self.currentDataFrame = 0
  def getBitDepth(self):
    return 12
  def getSize(self):
    return self.data.shape[1:]
  def listTransferModes(self):
    return ['mock']
  def getTransferMode(self):
    return 0
  def setTransferMode(self, mode):
    pass
  def listShutterModes(self):
    return ['mock']
  def getShutterMode(self):
    return 0
  def setShutterMode(self, mode):
    pass

  def start(self, frames=None, binning=None, exposure=None, region=None):
    self.ringSize = frames
    self.buf = numpy.empty((frames,) + self.data.shape[1:], dtype=numpy.uint16)
    return self.buf

  def lastFrame(self):
    nextDataFrame = int((time.time() % self.loopTime) * self.frameRate)
    if nextDataFrame >= self.data.shape[0]:
      nextDataFrame = self.data.shape[0]-1
    if self.currentDataFrame != nextDataFrame:
      self.currentBufferFrame = (self.currentBufferFrame + 1) % self.ringSize
      self.currentDataFrame = nextDataFrame
      self.buf[self.currentBufferFrame] = self.data[self.currentDataFrame]
      #print "Cam writing frame %d at %f" % (self.currentDataFrame, time.time())
    #print time.time(), self.currentBufferFrame, self.currentDataFrame
    return self.currentBufferFrame

  def stop(self):
    pass
