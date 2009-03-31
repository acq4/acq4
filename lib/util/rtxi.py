# -*- coding: utf-8 -*-
import sys, __main__
## Set to assist error message generation (some python internals expect sys.argv[0] to exist)
sys.argv = ['[RTXI]']

try:
  from __main__ import rtxiInterface
except:
  raise Exception("This script must be invoked from RTXI's embedded python interpreter.")
  
import types, os, re, socket, time, threading, scipy
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
          (pfx + "VRest", -60e-3, "VC resting potential to use between program calls"),
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
      
      ## default no interpolation
      if not ccmd[k].has_key('interpolate'):
        ccmd[k]['interpolate'] = False
      
      ## ?? Not sure why this was here.
      #if not ccmd[k].has_key("data"):
        #ccmd[k]["data"] = [[],[]]
        
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
    try:
      self.ri.runRtProgram(ccmd, runTime)
    except:
      print "Error executing program: (runTime=%f)" % runTime
      print ccmd
      raise
    
    ## get data generated during last run
    ## Data will be 2D array with time on axis 1 and columns on axis 0:
    ##   Time Ch0_requested Ch0_adjusted Ch0_output Ch0_input Ch1 ... Ch3
    ret = self.ri.getData()
    
    ## if any channels are in VC mode, set them back to resting potential
    for ch in ccmd.keys():
      if ccmd[ch]['mode'] == 'vc':
        vRest = self.getParam('rtxi.ch%d.VRest' % ch)
        self.setOutput(ch, vRest)
    
    chans = ccmd.keys() ##range(0,(len(ret)-1)/4)
    chans.sort()
    
    #names = ['time']
    #units = ['s']
    #axes = ['x']
    #columnIndex = [0]
    columnIndex = []
    
    ## decide which columns are interesting and label them
    info = [{'name': 'Signal', 'cols': []}, {'name': 'Time', 'units': 's'}]
    for chn in range(0, len(chans)):
      coln = 1+(chn*4)
      ch = chans[chn]
      if ccmd[ch]["mode"] in ['i=0', 'vc', 'ic', 'dc']:
        inpName = ccmd[ch]['signal']
        inpUnit = ccmd[ch]['units']
      
      if ccmd[ch]["mode"] == "i=0":
        columnIndex.append(coln+3)
        info[0]['cols'].extend([
          {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
        ])
      elif ccmd[ch]["mode"] == "vc":
        columnIndex.extend([coln, coln+1, coln+2, coln+3])
        info[0]['cols'].extend([
          {'name': "VReq%d" % ch, 'title': "ReqestedPotential%d" % ch, 'units': 'V'},
          {'name': "VAdj%d" % ch, 'title': "AdjustedPotential%d" % ch, 'units': 'V'},
          {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
          {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
        ])
      elif ccmd[ch]["mode"] == "ic":
        columnIndex.extend([coln, coln+1, coln+2, coln+3])
        info[0]['cols'].extend([
          {'name': "IReq%d" % ch, 'title': "ReqestedCurrent%d" % ch, 'units': 'A'},
          {'name': "IAdj%d" % ch, 'title': "AdjustedCurrent%d" % ch, 'units': 'A'},
          {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
          {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
        ])
      elif ccmd[ch]["mode"] == "dc":
        columnIndex.extend([coln, coln+1, coln+2, coln+3])
        info[0]['cols'].extend([
          {'name': "GReq%d" % ch, 'title': "ReqestedConductance%d" % ch, 'units': 'S'},
          {'name': "IAdj%d" % ch, 'title': "AdjustedCurrent%d" % ch, 'units': 'A'},
          {'name': "VOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
          {'name': "Inp%d" % ch, 'title': "%s%d" % (inpName, ch), 'units': inpUnit}
        ])
      elif ccmd[ch]["mode"] == "raw":
        columnIndex.extend([coln, coln+3])
        info[0]['cols'].extend([
          {'name': "Out%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
          {'name': "Inp%d" % ch, 'title': "InputVoltage%d" % ch, 'units': 'V'}
        ])
      else:
        columnIndex.extend([coln, coln+1, coln+2, coln+3])
        info[0]['cols'].extend([
          {'name': "SReq%d" % ch, 'title': "ReqestedSignal%d" % ch, 'units': ''},
          {'name': "SAdj%d" % ch, 'title': "AdjustedSignal%d" % ch, 'units': ''},
          {'name': "SOut%d" % ch, 'title': "OutputVoltage%d" % ch, 'units': 'V'},
          {'name': "Inp%d" % ch, 'title': "InputVoltage%d" % ch, 'units': 'V'}
        ])

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
    
    ## Copy time column to axis value array
    info[1]['values'] = ret[0,:]
    
    data = MetaArray(ret[columnIndex], info=info)
    return data
    
  def setOutput(self, channel, value, mode='vc'):
    cmd = {channel: {'mode': mode, 'data': [(0.0, value)], 'trigger': 0.0, 'interpolate': False}}
    self.ri.runRtProgram(cmd, 0.0)
  
  def plot(self, data, plotNum=0, plotRange=None):
    """Plot a MetaArray object. Most options are determined by the object.
    
      plotNum: The ID of the plot window to plot into
      plotRange: A list of range specifications which override the automatic range setting. 
                    [[left, right], [top0, bottom0], [top1, bottom1], ...]
                 To specify only one range, set the other to None:
                    [[left, right], None, ...]
    """
    
    lock = Locker(self.lock)
    pdata = data
    
    if type(data) == types.StringType:
      file = self.ri.getDataDir() + data
      if os.path.isfile(file):
        pdata = MetaArray(file=file)
      else:
        print "Can't find file %s" % file
    elif type(data) == types.ListType:
      if len(data) == 0:
        return
      if hasattr(data[0], '__float__'):
        pdata = MetaArray([[i, float(data[i])] for i in range(0, len(data))], info=[None, {'cols': [{'name': 'x'}, {'name': 'y'}]}])
      elif type(data[0]) == types.ListType:
        n = ['x']
        n.extend(["y%d"%i for i in range(1, len(data[0]))])
        pdata = MetaArray(data, info=[None, {'cols':[{'name': x} for x in n]}])
      else:
        raise Exception("Not sure how to plot that.")
    elif type(data) is MetaArray:
      # Move X-axis values into column 
      if data._info[1].has_key('values'):
        xv = data.xvals(1)
        i = data.infoCopy()
        del i[1]['values']
        i[0]['cols'] = [i[1]] + i[0]['cols']
        pdata = MetaArray(vstack([xv, data]), info=i)
        
    # Check and clean up the plotRange argument
    nc = pdata.shape[0]
    if plotRange is None:
      plotRange = [None] * nc
    elif type(plotRange) is types.ListType:
      if len(plotRange) > nc:
        raise Exception("plotRange list is too long")
      elif len(plotRange) < nc:
        plotRange.extend([None] * (nc-len(plotRange)))
        
      for i in range(0, len(plotRange)):
        if type(plotRange[i]) is types.ListType and len(plotRange[i]) == 2:
          plotRange[i] = [float(plotRange[i][0]), float(plotRange[i][1])]
        elif plotRange[i] is not None:
          raise Exception("Elements of plotRange list must be [float, float] or None")
    else:
      raise Exception("plotRange argument must be a list")
        
    self.ri.plot(pdata, plotNum, plotRange)
  
  
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






rtxi = Rtxi(rtxiInterface)