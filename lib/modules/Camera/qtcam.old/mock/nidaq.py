import mockdata, sys, time
from numpy import hstack

class MyMockNIDAQ:
  def __init__(self):
    self.data = mockdata.getMockData('cell')
    self.data = hstack([self.data, self.data])
    self.sampleRate = 20000.
    self.loopTime = 20.
    self.dataPtr = 0.0
  
  def __getattr__(self, attr):
    return lambda *args: self
  
  def listDevices(self):
    return ['mock0']
  
  def getDevice(self, ind):
    return self
  
  def listAIChannels(self):
    return ['one', 'two']
  
  def createTask(self, *args):
    return self
  
  def start(self):
    self.dataPtr = time.time()
  
  def read(self, size):
    dataLen = size / self.sampleRate
    dataEnd = self.dataPtr + dataLen
    now = time.time()
    if dataEnd > now:
      time.sleep(dataEnd-now)
    start = int((self.dataPtr % self.loopTime) * self.sampleRate)
    stop = int(start + size)
    self.dataPtr = dataEnd
    #print "read", start, stop
    #print "DAQ Returning %d:%d at %f" % (start, stop, time.time())
    return (self.data[:, start:stop], size)
  
  def GetReadAvailSampPerChan(self):
    return self.sampleRate * (time.time() - self.dataPtr)
    
  def stop(self):
    pass

NIDAQ = MyMockNIDAQ()

class ModWrapper(object):
  def __init__(self, wrapped):
    self.wrapped = wrapped

  def __getattr__(self, name):
    try:
      return getattr(self.wrapped, name)
    except AttributeError:
      if name[:3] == 'Val':
        return None
      else:
        return lambda *args: NIDAQ

sys.modules[__name__] = ModWrapper(sys.modules[__name__])
