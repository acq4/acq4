from functions import *
from ProtocolRunner import ProtocolRunner

class Experiment(ProtocolRunner):
  def __init__(self, rtxi, dm, channels={}):
    ProtocolRunner.__init__(self, rtxi)
    self._threads = []
    self.channels = channels
    self.rtxi = rtxi
    self.dm = dm.mkdir("exp", autoIndex=True, info=self._getExpInfo())
    
    ### Configure MC
    for ch in self.channels.keys():
      self.rtxi.mc.setParams(self.channels[ch], self.multiClampParams)
    
    
    ### Generate parameters
    
    
  def __del__(self):
    self.stopPeriodicCheck()
  
  def _getExpInfo(self):
    """Return a hash of information about this experiment instance to be stored with its data"""
    raise Exception("_getExpInfo() must be reimplemented in subclass.")
    
    
  def _getInitMulticlampParams(self):
    """Return a dict of initial parameters to configure the multiclamp with before patching begins."""
    raise Exception("_getInitMulticlampParams() must be reimplemented in subclass.")
  
  def _getRecordingParams(self):
    """return a list of all multiclamp parameters that should be recorded with every data file."""
    raise Exception("_getRecordingParams() must be reimplemented in subclass.")
    
  def startPeriodicCheck(self):
    pass
  
  def periodicCheck(self, iteration):
    raise Exception("periodicCheck() must be reimplemented in subclass.")
    
  def runTime(self):
    """Return the amount of time since the experiment began"""
    pass
    
  def checkMCState(self):
    pass
    ## Log the state of the multiclamp if possible
    ##   also clear the MC cache to make sure nothing unexpected is happening
    #mcState={}
    #try:
      #self.rtxi.mc.clearCache()
      #mcState = self.rtxi.mc.readParams(chan=0, params=recordParams, cache=False)
      ## If state doesn't agree with multiClampParams, then patching may have been done incorrectly.
      #diff = mcStateDiff(multiClampParams, mcState)
      #if len(diff) > 0:
        #raise Exception("Multiclamp not configured properly. Check %s" % diff)
      #rtxi.logMsg("MultiClamp parameters:\n%s" % str(res))
    #except:
      #rtxi.logMsg("Could not connect to multiclamp")
    
  def logMsg(self, msg, toGui=True):
    """Log a message to this experiment's logfile. Log to GUI window as well if requested."""
    self.dm.logMsg(msg)
    if toGui:
      self.rtxi.logMsg(msg)
  
  def startPeriodicCheck(self):
    """Start a thread which wakes up periodically to record the resting potential of the cell"""
    t = PeriodicThread(self)
    self._threads.append(t)
    t.start()
    
  def stopPeriodicCheck(self):
    for t in self._threads:
      print "Stopping thread %s" % t.getName()
      t.stopThread()
      t.join()
    self._threads = []
  
  def protocol(self):
    raise Exception("protocol() must be reimplemented in subclass.")
  
  def start(self):
    self.checkMCState()
    try:
      self.protocol()
    except:
      self.stopPeriodicCheck()
      raise
  
  
class HealthCheckThread(threading.Thread):
  def __init__(self, stp):
    self.stp = stp
    self.stop = False
    threading.Thread.__init__(self)

  def stopThread(self):
    self.stop = True
    
  def run(self):
    print "In thread!"
    lastCheckup = None
    start = time.time()
    results = []
    i = 0
    
    while True:
      if self.stop or self.stp.rtxi.checkEnd():
        break
      
      if lastCheckup is None or time.time()-lastCheckup > 60:
        lastCheckup = time.time()
        res = [lastCheckup-start]
        res.extend(list(self.stp.checkRestProperties(name="%d"%i, dirName="cellHealth")))
        results.append(res)
        print "Checkup %dsec: %0.3g, %0.3g, %0.3f" % tuple(res)
        i += 1
      
      time.sleep(1.0)
    
    a = array(results)
    d = MetaArray(a.transpose(), info=[axis(cols=[('Time', 's'),('MembranePotential', 'V'),('MP Deviation', 'V'), ('Spikes/Second', 'Hz')])])
    self.stp.rtxi.writeFile(d, 'cellHealthRecord', desc='Cell Health Record', dirName="cellHealth")
    print "Exit thread"
