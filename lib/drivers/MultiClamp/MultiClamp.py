# -*- coding: utf-8 -*-
import socket

class MultiClamp:
  """Class used to interface with remote multiclamp server"""
  
  
  ### state caching goodies for extra performance
  socket = None
  stateCache = {}
  useCache = False
  
  
  ## Functions that invalidate cached values of other parameters
  ## This list is probably incomplete.
  invalidRules = {
    "setMode": ["PrimarySignal", "SecondarySignal"],
    "setPrimarySignalByName": ['PrimarySignal'],
    "setSecondarySignalByName": ['SecondarySignal'],
    "setPrimarySignal": ["PrimarySignalInfo", "PrimarySignalByName", "PrimarySignalGain"],
    "setSecondarySignal": ["SecondarySignalInfo", "SecondarySignalByName", "SecondarySignalGain"]
  }
  
  ## Parameters to return when running prepareMultiClamp
  #recordParams = ['Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalGain', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']
  
  ## translate between RTXI modes and multiclamp modes
  modeTrans = {'vc': 'VC', 'ic': 'IC', 'dc': 'IC', 'i=0': 'I=0'}
  
  def __init__(self, host, port=34567):
      self.host = host
      self.port = port
  
  def __del__(self):
      self.disconnect()
  
  def disconnect(self):
      self.socket.close()
      
  
  def setUseCache(self, bool):
    """Set whether to use cache by default. Initialized to False, and can be overridden by individual function calls.
    
    Caching works this way: 
     - When a "get..." function is called, check for a cached value first.
       If one is available, return it. Otherwise, run the function and cache the value. 
     - When a "set..." function is called, check for a cached value first.
       If the cached value is the same as the requested value, just skip the remote call.
       If the remote call is necessary, run it and update the cached value.
       If the remote call affects other state variables, clear them out of the cache
         (for example, running setMode changes the value returned by getPrimarySignal)
     - If any remote call fails for any reason, clear the cached value.
    
    The cache is maintained at all times regardless of caching options. Setting the useCache parameter simply allows
    remote calls to be skipped if possible.
    Use with caution and understand the limitations of caching!
    """
    self.useCache = bool
  
  #def prepareMultiClamp(self, cmd, cache=None, returnState=False):
    #"""Sets the state of a remote multiclamp to prepare for a program run. This is called automatically by rtxi.runRtProgram()."""
    
    #state = {}
    #if cache is None: cache = self.useCache
    #for chan in cmd.keys():
      ##devId = self.getDevId(chan, cache=cache)
      #if devId == None:
        ### This channel has no remote counterpart to sync with
        #continue
      #mode = cmd[chan]["mode"]
      #if mode in ['raw', 'off', 'cb']:
        #continue
      ##mcMode = ''
      ##if mode in self.modeTrans.keys():
        ##mcMode = self.modeTrans[mode]
      ##else:
        ##print "Not sure how to prepare multiclamp for mode '%s'" % mode
        ##return False
      #self.setMode(chan, mode, cache=cache)
      ##self.runFunction('setMode', [devId, mcMode], cache=cache)
      ##print "prepareMultiClamp cache=", cache
      #self.runFunction('setPrimarySignalByName', (devId, cmd[chan]['signal']), cache=cache)
      #if returnState:
        #state[chan] = self.readParams(chan, self.recordParams, cache=cache)
        
    #return state
        


  ## Send small current/voltage signals and read to be sure the correct command was used
  #def testMultiClamp(self, chan, cache=None):
    #"""Sends small current/voltage signals to a remote multiclamp and analyzes the result to determine whether the multiclamp is properly configured. Should be run at the beginning of the day (at least)."""
    
    #tolerance = self.rtxi.getParam('rtxi.errorTolerance')
    
    #if cache is None: cache = self.useCache
    #tests = [
      #{'mode': 'vc', 'value': 10e-3, 'signal': 'MembranePotential'}, 
      #{'mode': 'ic', 'value': 5e-11, 'signal': 'MembraneCurrent'}] 
    #duration = 0.05
    #leadTime = 0.02
    
    #failures = []
    #errors = {}
    #for test in tests:
      
      ### generate program command
      #cmd = {chan: {
        #"mode": test['mode'], 
        #"data": [(0.0, 0.0), (leadTime+duration, test['value']), (leadTime+duration*2., 0.0)],
        #"trigger": 1e-3, 
        #"interpolate": False,
        #"signal": test['signal']}}
        
      ### Run program
      #data = self.rtxi.runRtProgram(cmd=cmd, runTime=2.*(leadTime+duration), useMCCache=False)
      
      ### Select out during and post-pulse ranges
      #ranges = []
      #ranges.append(data['Inp0', (data['Time'] > leadTime) * (data['Time'] < leadTime+duration)][1:])
      #ranges.append(data['Inp0', (data['Time'] > leadTime+duration) * (data['Time'] < leadTime+duration*2.)][1:])
      
      ### calculate means and check against requested values
      #avg = [x.mean() for x in ranges]
      #if abs(avg - test['value']) > abs(test['value'] * (tolerance * 0.01)):
        #test['avg'] = avg
        #failures.append(test)
      #errors[test['mode']] = (avg - test['value']) / test['value']
    #if len(failures) > 0:
      #l = ["%s(%g!=%g)" % (test['mode'], test['avg'], test['value']) for test in failures]
      #raise Exception("Multiclamp gain tests failed: %s" % ', '.join(l))
    #return errors


  def readParams(self, chan, params, cache=None):
    """Reads multiple parameters from a remote multiclamp.
    
    Arguments:
    chan -- Use the multiclamp device associated with this channel
    params -- List of parameters to request. 
              Each parameter "SomeValue" must have a corresponding remote function "getSomeValue"
    """
    
    if cache is None: cache = self.useCache
    res = {}
    #devId = self.getDevId(chan, cache=cache)
    #print "readParams cache=", cache
    for p in params:
      v = self.runFunction('get'+p, [chan], cache=cache)
      res[p] = v
    return res

  def setParams(self, chan, params, cache=None):
    """Sets multiple parameters on a remote multiclamp.
    
    Arguments:
    chan -- Use the multiclamp device associated with this channel
    params -- Dict of parameters to set. 
    """
    
    if cache is None: cache = self.useCache
    res = {}
    #devId = self.getDevId(chan, cache=cache)
    #print "setParams cache=", cache
    for p in params.keys():
      v = self.runFunction('set'+p, [chan, params[p]], cache=cache)
      res[p] = v
    return res
    



  #def getDevId(self, chan, cache=None):
    #"""Return the remote device ID for the device associated with channel. 
    
    #There must be a device identifier string (as returned by listRemoteDevices) in rtxi.chN.deviceDesc for this function to work. 
    #"""
    
    #if cache is None: cache = self.useCache
    ##print "getDevId cache=", cache
    #desc = rtxi.getParam('rtxi.ch%d.deviceDesc' % chan)
    #if len(desc) < 1:
      #return None
    
    #devList = self.listDevices(cache=cache)
    #try:
      #devNum = devList.index(desc)
      #return devNum
    #except:
      #print "Device description not found in current list"
      #return None
  
  def listDevices(self, cache=None):
    """Return a list of strings used to identify devices on a remote multiclamp server.
    
    These strings should be copied into the parameters rtxi.chN.deviceDesc (N is the channel number) to link a plugin channel to a remote headstage."""
    
    if cache is None: cache = self.useCache
    devList = []
    #print "listDevices cache=", cache
    nDev = int(self.runFunction('getNumDevices', cache=cache)[0])
    for i in range(0,nDev):
      desc = self.runFunction('getDeviceInfo', [i], cache=cache)
      strDesc = "model:%s,sn:%s,com:%s,dev:%s,chan:%s" % tuple(desc)
      devList.append(strDesc) 
    return devList
  
  def _getSocket(self, reset=False):
    """Return the network socket used to communicate with the remote multiclamp server."""
    
    if not reset and self.socket is not None:
      return self.socket
    socket.setdefaulttimeout(5.0)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((self.host, int(self.port)))
    self.socket = s
    return s
  
  def setMode(self, chan, mode, cache=None):
    if cache is None: cache = self.useCache
    self.runFunction('setMode', [chan, mode], cache=cache)
  
  def runFunction(self, func, args=(), maxResponse=1024, cache=None):
    """Run a function on a remote multiclamp server. 
    
    Function names are defined by the server and args must be a [list] of arguments. 
    For most functions, the first argument will be a device ID number.
    Example:
      rtxi.runFunction('getPrimarySignalGain', [rtxi.getDeviceId(0)])
      
    Always returns a list or raises exception if the server returned an error message.
    
    Arguments:
    maxResponse -- Maximum response length allowed
    cache -- If true, skip 'set' commands and use cached values for 'get' commands (use with caution!)
    """
    
    if cache is None: cache = self.useCache
    s = self._getSocket()
    strArgs = map(lambda x: str(x), args)
    #print "runFunction %s%s cache=%s" % (func, str(strArgs), str(cache))
    
    if cache:
      cval = self._searchCache(func, strArgs)
      if cval is not None:
        #print "  returning cached value:", str(cval)
        return cval
      #else:
        #print "  cache missed"
    
    cmd = "%s(%s)\n" % (func, ','.join(strArgs))
    try:
      s.send(cmd)
    except:
      s = self._getSocket(reset=True)
      s.send(cmd)
    resp = s.recv(maxResponse)
    data = resp.rstrip('\0\n').split(',')
    if func[:3] == 'get' and len(data) == 1:
      raise Exception("get returned no data: %s = %s <%s>" % (cmd, resp, str(data)))
    if data[0] == '0':
      self._invalidateCache(func, strArgs)
      raise Exception('MultiClamp communication error: %s' % data[1])
    else:
      self._updateCache(func, strArgs, data[1:])
      return data[1:]
        
  def __getattr__(self, attr):
      return lambda *args: self.runFunction(attr, args)
  
  def getSignalInfo(self, chan, outputChan='Primary', cache=None):
    """Return a tuple (signalName, gain, units) for the current signal
    
    the outputChan argument defaults to 'Primary' and can be set to 'Secondary' instead.
    """
    #print "getSignalInfo cache=", cache
    if cache is None: cache = self.useCache
    #dID = self.getDevId(chan, cache=cache)
    (name, gain, units) = self.runFunction('get%sSignalInfo' % outputChan, [chan], cache=cache)
    if outputChan == 'Primary':
        xGain = float(self.runFunction('get%sSignalGain' % outputChan, [chan], cache=cache)[0])
    else:
        xGain = 1.0
    gain2 = float(gain) * xGain
    #print "%s gain = %f * %f = %f" % (outputChan, float(gain), float(xGain[0]), gain2)
    return (name, gain2, units)
  
  def clearCache(self):
    self.stateCache = {}
  
  
  def _updateCache(self, func, args, result):
    (mode, cKey, xKey, setRes) = self._cacheKey(func, args)
    cKey = cKey+xKey
    if mode == 'set':
      result = setRes
      self._invalidateCache(func, args)
    elif mode != 'get':
      return
    #print "  caching %s" % cKey
    if len(result) < 1:
      raise Exception("Caught faulty set %s(%s) => %s=%s" % (func, str(args), cKey, str(result)));
    #print "    setting cache[%s] = %s" % (cKey, str(result))
    self.stateCache[cKey] = result
    
  def _searchCache(self, func, args):
    (mode, cKey, xKey, setRes) = self._cacheKey(func, args)
    cKey = cKey+xKey
    if mode == 'set':
      if self.stateCache.has_key(cKey) and self.stateCache[cKey] == setRes:
        return []
    elif mode == 'get':
      if self.stateCache.has_key(cKey):
        return self.stateCache[cKey]
      #else:
        #print "    cache has no get key %s" % cKey
    return None
    
  def _invalidateCache(self, func, args, inv=None):
    if func not in self.invalidRules.keys():
      return inv
    
    (mode, cKey, xKey, setRes) = self._cacheKey(func, args)
    if inv is None:
      inv = [func]
    for n in self.invalidRules[func]:
      fnName = "set"+n
      if fnName not in inv:
        inv.append(fnName)
        inv = self._invalidateCache(fnName, args, inv)
      #print "  clearing %s" % n
      if self.stateCache.has_key(n+xKey):
        #print "    removing %s from cache" % (str(n+xKey))
        self.stateCache.pop(n+xKey)
    return inv
    
  def _cacheKey(self, func, args):
    if func[:3] == 'set' and len(args) == 2:
      xKey = '_' + args[0]
      cKey = func[3:]
      return ('set', cKey, xKey, args[1])
    elif func[:3] == 'get':
      xKey = '_' + '_'.join(args)
      cKey = func[3:]
      return ('get', cKey, xKey, None)
    else:
      return None
    
  def stateDiff(self, state):
    """Compare the state of the multiclamp to the expected state (s1), return the keys that differ."""
    m = []
    for k in state.keys():
      v = state[k]
      if type(v) == types.BooleanType:
        if (v and s2[k][0] != 'true') or (not v and s2[k][0] != 'false'):
          m.append(k)
      elif type(v) == types.IntType:
        if v != int(s2[k][0]):
          m.append(k)
      elif type(v) == types.FloatType:
        if v - float(s2[k][0]) > 1e-30:
          m.append(k)
    return m
    