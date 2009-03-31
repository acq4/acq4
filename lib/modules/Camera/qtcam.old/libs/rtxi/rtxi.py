import sys
## Set to assist error message generation (some python internals expect sys.argv[0] to exist)
sys.argv = ['[RTXI]']

try:
  from __main__ import rtxiInterface
except:
  raise Exception("This script must be invoked from RTXI's embedded python interpreter.")
  
#from rtxilib import *
import types, os, re, socket, time, threading
from MetaArray import *
from functions import *

class Rtxi:
  """This class provides the interface to the dynamic clamp plugin in RTXI. It extends the rtxi object defined in the dynamic clamp plugin, and can not be used on its own.
  
  The most useful functions are runRtProgram and plot. For example, rtxi.plot(rtxi.runRtProgram(mode='i=0', runTime=0.1))
  Functions that interact with the parameter list are getParam, setParam, setParamDefault, and registerParams
  Functions that communicate with a remote multiclamp server are under rtxi.mc"""
  
  ri = None
  params = {}
  callbacks = {}
  cbArgs = {}
  
  
  def __init__(self, rInt):
    """This constructor should only be called by RTXI, never by the user."""
    self.ri = rInt
    self.expNum = None
    self.mc = MultiClamp(self)
    self.lock = threading.RLock()
    
    ## Copy all public-looking functions from RTXI object
    for f in dir(self.ri):
      if f[0] != '_' and not hasattr(self, f):
        setattr(self, f, getattr(self.ri, f))
        
    ## Save and override stdout/stderr so we can redirect print statements
    self.stdout = sys.stdout
    sys.stdout = self
    self.stderr = sys.stderr
    sys.stderr = self
        
    
    ## Set up variables that tell RTXI how to communicate with the amplifier
    try:
      self.getParam('rtxi')
    except:
      for i in range(0,4):
        pfx = "rtxi.ch%d." %i
        params = [
          (pfx + "deviceDesc", "", "Device description string linking this\nchannel to a device in the MultiClamp\nserver (see rtxi.listRemoteDevices)"),
          (pfx + "vc.cmdGain", 20e-3, "(V/V) Scaling factor for voltage command\nas configured in the commander software.\nThis value is NOT communicated with the server, it must be set manually.\nThis value is probably either 0.02 or 0.1"),
          (pfx + "vc.limit", 0.5, "(V) Maximum absolute voltage command allowed\nin VC mode. The check is performed before scaling."),
          #(pfx + "vc.scaledOutMode", "VC_MEMBCURRENT", "Output mode for the amplifier's \"scaled output\""),
          #(pfx + "vc.outputGain", 50, "Output gain for VC mode as configured in\ncommander software. Probably should be one of:\n(1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000)"),
          #(pfx + "vc.outputConvert", 0.5e9, "(V/A) Factor used to convert current into a\nvoltage signal BEFORE output gain is applied.\nThis is not communicated with the server, and is probably\nalways 0.5V/nA (I don't think this is configurable)"),
          (pfx + "ic.cmdGain", 400e-12, "(A/V) Scaling factor for current command as\nconfigured in the commander software. This value is\nNOT communicated with the server, it must be set manually.\nThis value is probably either 400e-12 or 2e-9"),
          (pfx + "ic.limit", 1e-6, "(A) Maximum absolute current command allowed\nin IC mode. The check is performed before scaling."),
          #(pfx + "ic.scaledOutMode", "VC_PIPPOTENTIAL", "Output mode for the amplifier's \"scaled output\""),
          #(pfx + "ic.outputGain", 50, "Output gain for IC mode as configured in\ncommander software. Probably should be one of:\n(1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000)"),
          (pfx + "reversalPotential", 0.0, "Reversal potential for simple membrane model in DC mode"),
        ]
        self.registerParams(params)
        
      self.registerParams([
        ("rtxi.errorTolerance", 10., "(%) Tolerance for errors detected while running testMultiClamp.\nThe function will raise an exception if the error measured is larger than this value."),
        ("rtxi.multiClampHost", "", "hostname:port of MultiClamp server")
      ])
    
    
  ## Extend a few functions
  
  def runRtProgram(self, mode=None, data=None, runTime=None, trigger=None, cmd=None, interpolate=False, signal=None, useMCCache=None, channel=0, fullInfo=True):
    """Runs a realtime program. 
    
    You may specify the mode and waveform for each channel. Takes some complex
    options in various forms. The easiest to use is: 
      runRtProgram(mode, [data], runTime)
    or with named parameters like:
      runRtProgram(mode="ic", data=[...], trigger=True, runTime=..)
    similarly, you can specify the entire command in the "cmd" argument:
      runRtProgram(cmd={"mode": "ic", "data": [...], ...}, runTime=..)
    All three of the previous examples default to using channel 0. You may
    also specify multiple channel commands:
      runRtProgram( cmd = {
                            0: {"mode": "ic", "data": [...], ...},
                            1: {"mode": "i=0", ...}
                          }, runTime=..)
    
    Arguments:
    mode -- Must be one of: 'ic', 'i=0', 'vc', 'dc', or 'cb'
    data -- Must be a list of (time,value) pairs that make up the command 
            waveform
    runTime -- The total time the program should run for in seconds
    channel -- The channel to use for single-channel programs. Defaults to 0 
               and is ignored for multi-channel commands.
    interpolate -- If true, the command waveform is linearly interpolated 
                   (default True)
    trigger -- Length of time to activate trigger at beginning of command
               (default 1ms)
    signal -- The signal to record at the multiclamp. This value is set by
              default depending on the mode
    useMCCache -- Set to true to allow the multiclamp interface to rely on
                  cached values rather than making calls to the server
                  (use with caution)
    fullInfo -- Include lots of meta-information with the returned results.
                Default is True, can be disabled to improve performance.
    
    Returns a MetaArray object.
    """
    lock = Locker(self.lock)
    
    pTypes = ["off", "raw", "i=0", "vc", "ic", "dc", "cb"]
    if runTime == None:
      raise Exception("Must specify maximum run time for program")
    
    ccmd = {}
    ## Clean up the command a bit
    if cmd != None:
      if cmd.has_key("mode"):
        # command is for one channel only
        ccmd[channel] = cmd
      else:
        # multiple-channel command
        ccmd = cmd
    else:
      if mode != None and (data != None or mode == "i=0"):
        ccmd[channel] = {"mode": mode, "data": data, "trigger": trigger, "interpolate": interpolate}
      else:
        raise Exception("Invalid options :(")
      
    for k in ccmd.keys():
      if not ccmd[k].has_key("mode") or not ccmd[k]["mode"] in pTypes:
        raise Exception("Unknown mode in command")
      
      ## Default 1ms trigger length
      if not ccmd[k].has_key("trigger") or ccmd[k]["trigger"] == None or ccmd[k]["trigger"] == True:
        ccmd[k]["trigger"] = 1.0e-3  
        
      ## ?? Not sure why this is here.
      if not ccmd[k].has_key("data"):
        ccmd[k]["data"] = [[],[]]
        
      #if len(ccmd[k]['data']) < 1:
        #raise Exception("Empty command data list not allowed.")
        
      ## Decide which signal to record if none was specified
      if mode != "raw" and not ccmd[k].has_key('signal'):
        if signal == None:
          if ccmd[k]['mode'] == 'vc':
            ccmd[k]['signal'] = "MembraneCurrent"
          elif ccmd[k]['mode'] in ['i=0', 'ic', 'dc']:
            ccmd[k]['signal'] = "MembranePotential"
          else:
            ccmd[k]['signal'] = None
      if ccmd[k]['mode'] == 'dc' and ccmd[k]['signal'] != 'MembranePotential':
        raise Exception("Dynamic clamp mode requires signal='MembranePotential'")
      
    
    ## Make sure MC is in the correct mode and all gain options are consistent
    mcState = self.mc.prepareMultiClamp(ccmd, cache=useMCCache, returnState=fullInfo)
    
      ## Get info about current signal
    for k in ccmd.keys():
      if ccmd[k]['mode'] == 'raw' or self.getParam('rtxi.ch%d.deviceDesc'%k) == '':
        ccmd[k]['outputScale'] = 1.
        ccmd[k]['units'] = 'V'
      else:
        (name, gain, units) = self.mc.getSignalInfo(k, cache=useMCCache)
        ccmd[k]['outputScale'] = 1. / gain
        ccmd[k]['units'] = units
      
    
    ## Run the program
    startTime = time.time()
    self.ri.runRtProgram(ccmd, runTime)
    ret = self.ri.getData()
    chans = ccmd.keys() ##range(0,(len(ret)-1)/4)
    
    names = ['time']
    units = ['s']
    axes = ['x']
    columnIndex = [0]
    
    ## decide which columns are interesting and label them
    info = [{'name': 'Signal', 'cols': [{'name': 'Time', 'units': 's'}]}, {'name': 'Time'}]
    chans.sort()
    for chn in range(0, len(chans)):
      ch = chans[chn]
      if ccmd.has_key(ch):
        
        if ccmd[ch]["mode"] in ['i=0', 'vc', 'ic', 'dc']:
          inpName = ccmd[ch]['signal']
          inpUnit = ccmd[ch]['units']
        
        if ccmd[ch]["mode"] == "i=0":
          columnIndex.append(ch+4)
          info[0]['cols'].extend([
            {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
          ])
        elif ccmd[ch]["mode"] == "vc":
          columnIndex.extend([chn+1, chn+2, chn+3, chn+4])
          info[0]['cols'].extend([
            {'name': "VReq%d" % ch, 'title': "ReqestedPotential%d" % ch, 'units': 'V'},
            {'name': "VAdj%d" % ch, 'title': "AdjustedPotential%d" % ch, 'units': 'V'},
            {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
            {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
          ])
        elif ccmd[ch]["mode"] == "ic":
          columnIndex.extend([chn+1, chn+2, chn+3, chn+4])
          info[0]['cols'].extend([
            {'name': "IReq%d" % ch, 'title': "ReqestedCurrent%d" % ch, 'units': 'A'},
            {'name': "IAdj%d" % ch, 'title': "AdjustedCurrent%d" % ch, 'units': 'A'},
            {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
            {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
          ])
        elif ccmd[ch]["mode"] == "dc":
          columnIndex.extend([chn+1, chn+2, chn+3, chn+4])
          info[0]['cols'].extend([
            {'name': "GReq%d" % ch, 'title': "ReqestedConductance%d" % ch, 'units': 'S'},
            {'name': "IAdj%d" % ch, 'title': "AdjustedCurrent%d" % ch, 'units': 'A'},
            {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
            {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
          ])
        elif ccmd[ch]["mode"] == "raw":
          columnIndex.extend([chn+1, chn+4])
          info[0]['cols'].extend([
            {'name': "Out%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
            {'name': "Inp%d" % ch, 'title': "InputVoltage%d" % ch, 'units': 'V'}
          ])
        else:
          print "WARNING: Not post-processing data for mode '%s'" % ccmd[ch]['mode']
          ### Add room for 4 more columns

    ## Add more experimental parameters to info array:
    ##   target period, runTime
    ##   for each channel:
    ##     interpolate, trigger, mode, primary signal, gain, pip. offset, bridge balance, cap. comp.
    if fullInfo:
      chInfo = {}
      for ch in chans:
        mcInfo = None
        if mcState.has_key(ch):
          mcInfo = mcState[ch]
        chInfo[ch] = {
          'interpolate': ccmd[ch]['interpolate'],
          'trigger': ccmd[ch]['trigger'],
          'cmdMode': ccmd[ch]['mode'],
          'mcInfo': mcInfo
        }
      info.append({'period': self.getPeriod(), 'runTime': runTime, 'startTime': startTime, 'channelInfo': chInfo})

    data = MetaArray(ret[columnIndex], info=info)
    return data
    
  def plot(self, data):
    """Plot a MetaArray object. All options are determined by the object."""
    
    lock = Locker(self.lock)
    if type(data) == types.StringType:
      file = self.ri.getDataDir() + data
      if os.path.isfile(file):
        ds = MetaArray(file=file)
        self.ri.plot(ds)
      else:
        print "Can't find file %s" % file
    elif type(data) == types.ListType:
      if len(data) == 0:
        return
      if hasattr(data[0], '__float__'):
        ds = MetaArray([[i, float(data[i])] for i in range(0, len(data))], info=[None, {'cols': [{'name': 'x'}, {'name': 'y'}]}])
        self.ri.plot(ds)
      elif type(data[0]) == types.ListType:
        n = ['x']
        n.extend(["y%d"%i for i in range(1, len(data[0]))])
        ds = MetaArray(data, info=[None, {'cols':[{'name': x} for x in n]}])
        self.ri.plot(ds)
      else:
        raise Exception("Not sure how to plot that.")
    else:
      self.ri.plot(data)
  
  
  def ls(self, d=None):
    """List the files in the directory specified. If d=None, use getDataDir() to determine the directory to use."""
    if d == None:
      d = self.getDataDir()
    if not os.path.isdir(d):
      d = self.getDataDir() + '/' + d
      if not os.path.isdir(d):
        raise Exception("Path \"%s\" does not exist" % d)
    files = os.listdir(d)
    
    ## Compare all numbers in the file name numerically
    def numcmp(a, b):
      am = re.findall(r'(-?\d+(\.\d*)?((e|E)-?\d+)?)', a)
      bm = re.findall(r'(-?\d+(\.\d*)?((e|E)-?\d+)?)', b)
      if len(am) > 0 and len(bm) > 0:
        for i in range(0, len(am)):
          c = cmp(float(am[i][0]), float(bm[i][0]))
          if c != 0:
            return c
      return cmp(a, b)
    
    files.sort(numcmp)
    if len(files) > 0:
      #self.ri.logMsg("Files in %s:" % d)
      #self.ri.logMsg(" ".join(["<a href=\"%s/%s\">%s</a>"%(d, f, f) for f in files]))
      self.write("Files in %s:\n" % d, allowHtml=True)
      self.write(" ".join(["<a href=\"%s/%s\">%s</a>"%(d, f, f) for f in files]) + "\n", allowHtml=True)
    
  def nextExpNumber(self):
    """Return the next available experiment number by looking through the files in dataDir."""
    dataDir = self.getDataDir()
    maxNum = 0
    files = os.listdir(dataDir)
    for f in files:
      match = re.match(r"exp(\d{3})", f)
      if match != None:
        maxNum = max(maxNum, int(match.group(1)))
    return maxNum+1

  def expNumber(self):
    """Return the current experiment number."""
    
    if self.expNum == None:
      self.expNum = self.nextExpNumber()
    return self.expNum

  def newExperiment(self):
    """Increment experiment number to the next unused value."""
    
    self.expNum = None
    self.logMsg("Starting experiment #%03d" % self.expNumber())

  def write(self, strng, allowHtml = False):
    """Write a message into the experiment log."""
    
    strng = str(strng)
    if( not allowHtml ):
      strng = re.sub('&', '&amp;', strng)
      strng = re.sub('<', '&lt;', strng)
      strng = re.sub('>', '&gt;', strng)
    strng = re.sub(r'\n([^$])', r'<br>\1', strng)  ## convert newlines into <br> EXCEPT the last one.
    
    self.ri.write(str(strng))
    
  def writeFile(self, ds, name, desc="", dirName=""):
    """Write a MetaArray to disk under the current experiment directory.
    
    Arguments:
    ds -- The MetaArray object
    name -- File name to write
    desc -- Description of file for log
    dirName -- Optional subdirectory name
    """
    
    dataDir = self.getDataDir() + "/" + "exp%03d" % self.expNumber()
    
    if dirName != "":
      dataDir += "/" + dirName
    try:
      os.makedirs(dataDir)
    except Exception, e:
      if e.errno != 17:
        raise e
    else:
      self.logMsg('Created directory <a href="%s">%s</a>' % (dataDir, dataDir))
      
    url = dataDir + "/" + name
    ds.write(url)
    if desc != None:
      if desc != "":
        desc += " "
      self.logMsg('Wrote %sfile to <a href="%s">%s</a>' % (desc, url, name))
    
  def registerParams(self, params, prefix=""):
    """Set default values for multiple parameters. Argument is a list of (name, value, [description]) tuples."""
    
    if type(params) is types.DictType:
      for name in params.keys():
        v = params[name]
        if len(v) == 1:
          val = v[0]
          desc = ""
        elif len(v) == 2:
          (val, desc) = v
        self.setParamDefault(prefix+name, val, desc)
    else:
      for r in params:
        if len(r) == 2:
          (name, val) = r
          desc = ""
        elif len(r) == 3:
          (name, val, desc) = r
        self.setParamDefault(prefix+name, val, desc)
        
  def setParamDefault(self, *args):
    #print args
    self.ri.setParamDefault(*args)
        
  def linkClicked(self, url):
    """Used by the plugin to handle a link click in the log window. Lists files in a directory or plots the contents of a file."""
    
    if os.path.isfile(url):
      self.plot(MetaArray(file=url))
    elif os.path.isdir(url):
      self.ls(url)
      
  def registerCallback(self, name, fn, *args):
    """Register a callback function with the plugin. The name will be added to the dropdown list of protocols available."""
    
    if not self.callbacks.has_key(name):
      self.ri.registerCallback(name)
    self.callbacks[name] = fn
    self.cbArgs[name] = args
  
  def runCallback(self, name):
    """Used by the plugin to run a callback function."""
    try:
      self.callbacks[name](*self.cbArgs[name])
    except Exception, e:
      if e.message == 'USER_ABORT':
        print "Aborting %s by request" % name
      else:
        raise
      
  def askDialog(self, fields):
    """Generate a dialog box for asking questions, return the results after OK is clicked."""
    
    if type(fields) is not types.ListType or len(fields) < 1:
      raise Exception('Fields parameter must be a list of names or dicts.')
    
    
    import qt
    
    ### This function is complex because only the GUI thread is allowed to perform GUI operations. 
    ### To get around this, we define the operations here and then request that the GUI thread run them for us.
    
    # Cross-thread storage, just an empty class
    class Obj:
      pass
    s = Obj()
    s.qwc = qt.QWaitCondition()
    
    ## Define dialog. All objects must be members of the predefined storage object
    ## so that they are available to both threads.
    def mkDlg():
      ## Generate dialog
      s.dlg = qt.QDialog()
      s.vbl = qt.QVBoxLayout(s.dlg)
      
      s.grid = qt.QGridLayout(None,1,1,0,len(fields))
      s.labels = []
      s.widgets = []
      for i in range(0, len(fields)):
        if type(fields[i]) is types.DictType:
          pass
        elif type(fields[i]) is types.StringType:
          fields[i] = {'name': fields[i], 'type': 'textline'}
        else:
          s.qwc.wakeAll()
          raise Exception('Incorrect arguments (index %d)' % i)
        
        s.labels.append(qt.QLabel(s.dlg))
        s.labels[-1].setText(fields[i]['name'])
        s.grid.addWidget(s.labels[-1], i, 0)
        
        if not fields[i].has_key('type'):
          fields[i]['type'] = 'textline'
          
        if fields[i]['type'] == 'textline':
          s.widgets.append(qt.QLineEdit(s.dlg))
          if fields[i].has_key('default'):
            s.widgets[-1].setText(fields[i]['default'])
        elif fields[i]['type'] == 'textbox':
          s.widgets.append(qt.QTextEdit(s.dlg))
          if fields[i].has_key('default'):
            s.widgets[-1].setText(fields[i]['default'])
        else:
          s.qwc.wakeAll()
          raise Exception('Bad input type "%s"' % str(fields[i]['type']))
          
        s.grid.addWidget(s.widgets[-1], i, 1)
      s.btn = qt.QPushButton(s.dlg)
      s.btn.setText('OK')
      s.vbl.addLayout(s.grid)
      s.vbl.addWidget(s.btn)
      
      qt.QObject.connect(s.btn, qt.SIGNAL("clicked()"), s.qwc.wakeAll)
      s.dlg.show()
      
    ## Request the GUI thread to generate the dialog
    self.guiCall(mkDlg)
    
    ## Wait for OK click
    s.qwc.wait()
    
    # Collect and return results
    result = {}
    for i in range(0, len(fields)):
      if fields[i]['type'] == 'textline' or fields[i]['type'] == 'textbox':
        result[fields[i]['name']] = str(s.widgets[i].text())
    
    ## Request GUI thread to destroy dialog
    def fn():
      del s.dlg
    self.guiCall(fn)
    
    return result

  def checkEnd(self, exception=True):
    end = self.ri.checkEnd()
    if end and exception:
      raise Exception("USER_ABORT")
    else:
      return end





class MultiClamp:
  """Class used to interface with remote multiclamp server"""
  
  
  ### state caching goodies for extra performance
  socket = None
  stateCache = {}
  useCache = False
  
  
  ## Functions that invalidate other parameters
  ## This list is probably incomplete.
  invalidRules = {
    "setMode": ["PrimarySignal", "SecondarySignal"],
    "setPrimarySignalByName": ['PrimarySignal'],
    "setSecondarySignalByName": ['SecondarySignal'],
    "setPrimarySignal": ["PrimarySignalInfo", "PrimarySignalByName", "PrimarySignalGain"],
    "setSecondarySignal": ["SecondarySignalInfo", "SecondarySignalByName", "SecondarySignalGain"]
  }
  
  ## Parameters to return when running prepareMultiClamp
  recordParams = ['Holding', 'HoldingEnable', 'PipetteOffset', 'FastCompCap', 'SlowCompCap', 'FastCompTau', 'SlowCompTau', 'NeutralizationEnable', 'NeutralizationCap', 'WholeCellCompEnable', 'WholeCellCompCap', 'WholeCellCompResist', 'RsCompEnable', 'RsCompBandwidth', 'RsCompCorrection', 'PrimarySignalGain', 'PrimarySignalLPF', 'PrimarySignalHPF', 'OutputZeroEnable', 'OutputZeroAmplitude', 'LeakSubEnable', 'LeakSubResist', 'BridgeBalEnable', 'BridgeBalResist']
  
  ## translate between RTXI modes and multiclamp modes
  modeTrans = {'vc': 'VC', 'ic': 'IC', 'dc': 'IC', 'i=0': 'I=0'}
  
  def __init__(self, rtxi):
    self.rtxi = rtxi
  
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
  
  def prepareMultiClamp(self, cmd, cache=None, returnState=False):
    """Sets the state of a remote multiclamp to prepare for a program run. This is called automatically by rtxi.runRtProgram()."""
    
    state = {}
    if cache is None: cache = self.useCache
    for chan in cmd.keys():
      devId = self.getDevId(chan, cache=cache)
      if devId == None:
        ## This channel has no remote counterpart to sync with
        continue
      mode = cmd[chan]["mode"]
      if mode in ['raw', 'off', 'cb']:
        continue
      mcMode = ''
      if mode in self.modeTrans.keys():
        mcMode = self.modeTrans[mode]
      else:
        print "Not sure how to prepare multiclamp for mode '%s'" % mode
        return False
      self.runFunction('setMode', [devId, mcMode], cache=cache)
      self.runFunction('setPrimarySignalByName', (devId, cmd[chan]['signal']), cache=cache)
      if returnState:
        state[chan] = self.readParams(chan, self.recordParams, cache=cache)
        
    return state
        


  ## Send small current/voltage signals and read to be sure the correct command was used
  def testMultiClamp(self, chan, cache=None):
    """Sends small current/voltage signals to a remote multiclamp and analyzes the result to determine whether the multiclamp is properly configured. Should be run at the beginning of the day (at least)."""
    
    tolerance = self.rtxi.getParam('rtxi.errorTolerance')
    
    if cache is None: cache = self.useCache
    tests = [
      {'mode': 'vc', 'value': 10e-3, 'signal': 'MembranePotential'}, 
      {'mode': 'ic', 'value': 5e-11, 'signal': 'MembraneCurrent'}] 
    duration = 0.05
    leadTime = 0.02
    
    failures = []
    errors = {}
    for test in tests:
      
      ## generate program command
      cmd = {chan: {
        "mode": test['mode'], 
        "data": [(0.0, 0.0), (leadTime+duration, test['value']), (leadTime+duration*2., 0.0)],
        "trigger": 1e-3, 
        "interpolate": False,
        "signal": test['signal']}}
        
      ## Run program
      data = self.rtxi.runRtProgram(cmd=cmd, runTime=2.*(leadTime+duration), useMCCache=False)
      
      ## Select out during and post-pulse ranges
      ranges = []
      ranges.append(data['Inp0', (data['Time'] > leadTime) * (data['Time'] < leadTime+duration)][1:])
      ranges.append(data['Inp0', (data['Time'] > leadTime+duration) * (data['Time'] < leadTime+duration*2.)][1:])
      
      ## calculate means and check against requested values
      avg = [x.mean() for x in ranges]
      if abs(avg - test['value']) > abs(test['value'] * (tolerance * 0.01)):
        test['avg'] = avg
        failures.append(test)
      errors[test['mode']] = (avg - test['value']) / test['value']
    if len(failures) > 0:
      l = ["%s(%g!=%g)" % (test['mode'], test['avg'], test['value']) for test in failures]
      raise Exception("Multiclamp gain tests failed: %s" % ', '.join(l))
    return errors


  def readParams(self, chan, params, cache=None):
    """Reads multiple parameters from a remote multiclamp.
    
    Arguments:
    chan -- Use the multiclamp device associated with this channel
    params -- List of parameters to request. 
              Each parameter "SomeValue" must have a corresponding remote function "getSomeValue"
    """
    
    if cache is None: cache = self.useCache
    res = {}
    devId = self.getDevId(chan, cache=cache)
    for p in params:
      v = self.runFunction('get'+p, [devId], cache=cache)
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
    devId = self.getDevId(chan, cache=cache)
    for p in params.keys():
      v = self.runFunction('set'+p, [devId, params[p]], cache=cache)
      res[p] = v
    return res
    



  def getDevId(self, chan, cache=None):
    """Return the remote device ID for the device associated with channel. 
    
    There must be a device identifier string (as returned by listRemoteDevices) in rtxi.chN.deviceDesc for this function to work. 
    """
    
    if cache is None: cache = self.useCache
    desc = rtxi.getParam('rtxi.ch%d.deviceDesc' % chan)
    if len(desc) < 1:
      return None
    
    devList = self.listDevices(cache=cache)
    try:
      devNum = devList.index(desc)
      return devNum
    except:
      print "Device description not found in current list"
      return None
  
  def listDevices(self, cache=None):
    """Return a list of strings used to identify devices on a remote multiclamp server.
    
    These strings should be copied into the parameters rtxi.chN.deviceDesc (N is the channel number) to link a plugin channel to a remote headstage."""
    
    if cache is None: cache = self.useCache
    devList = []
    nDev = int(self.runFunction('getNumDevices', cache=cache)[0])
    for i in range(0,nDev):
      desc = self.runFunction('getDeviceInfo', [i], cache=cache)
      strDesc = "model:%s,sn:%s,com:%s,dev:%s,chan:%s" % tuple(desc)
      devList.append(strDesc) 
    return devList
  
  def _getSocket(self, reset=False):
    """Return the network socket used to communicate with the remote multiclamp server. Depends on the parameter rtxi.multiClampHost"""
    
    if not reset and self.socket is not None:
      return self.socket
    try:
      host = rtxi.getParam('rtxi.multiClampHost')
      (host, port) = host.split(':')
    except:
      raise Exception("Invalid hostname, cannot connect to multiclamp server")
    socket.setdefaulttimeout(5.0)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, int(port)))
    self.socket = s
    return s
  
  def setMode(self, chan, mode, cache=None):
    if cache is None: cache = self.useCache
    devId = self.getDevId(chan)
    if self.modeTrans.has_key(mode):
      self.runFunction('setMode', [devId,self.modeTrans[mode]])
    else:
      raise Exception("Unknown multiclamp mode '%s'" % mode) 
  
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
    
    if cache:
      cval = self._searchCache(func, strArgs)
      if cval is not None:
        #print "  returning %s cached" % func
        return cval
    
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
        
  
  def getSignalInfo(self, chan, outputChan='Primary', cache=None):
    """Return a tuple (signalName, gain, units) for the current signal
    
    the outputChan argument defaults to 'Primary' and can be set to 'Secondary' instead.
    """
    
    if cache is None: cache = self.useCache
    dID = self.getDevId(chan, cache=cache)
    (name, gain, units) = self.runFunction('get%sSignalInfo' % outputChan, [dID], cache=cache)
    xGain = self.runFunction('get%sSignalGain' % outputChan, [dID], cache=cache)
    gain = float(gain) * float(xGain[0])
    return (name, gain, units)
  
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
    
rtxi = Rtxi(rtxiInterface)