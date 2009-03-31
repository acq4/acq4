import functions
import time
from MetaArray import *
from Protocol import Protocol
#from scipy import *


class Scope(Protocol):
  parameters = {
    'Channel': (0, "Channel to record from"),
    'Duration': (100e-3, "Time to record each cycle"), 
    'WaitTime': (0.01, "Time to wait between cycles"), 
  }
  def run(self):
    useCache = False
    while True:
      self.rtxi.checkEnd()
      rec = self.rtxi.runRtProgram(
        channel=self.Channel, 
        mode="i=0", 
        runTime=self.Duration, 
        useMCCache=useCache, 
        fullInfo=False
      )
      self.rtxi.plot(rec)
      time.sleep(self.WaitTime)
      useCache = True


class CCPatchPulse(Protocol):
  parameters = {
    "Channel": (0, "Channel to interact with"),
    "Amplitude": (-50e-12, "Square pulse amplitude"),
    "LeadTime": (5e-3, "Delay to pulse start"),
    "PulseWidth": (100e-3, "Square pulse duration"),
    "LagTime": (125e-3, "Delay after pulse ends"),
    "WaitTime": (200e-3, "Time between pulses")
  }
  def run(self):
    useCache = False
    while True:
      self.rtxi.checkEnd()
      cmd = [[0.0, 0.0], [self.LeadTime, self.Amplitude], [self.LeadTime+self.PulseWidth, 0.0]]
      res = self.rtxi.runRtProgram(
        channel=self.Channel,
        mode="ic", 
        data=cmd, 
        runTime=self.LeadTime + self.PulseWidth + self.LagTime, 
        useMCCache=useCache,
        fullInfo=False
      )
      self.rtxi.plot(res)
      useCache = True
      time.sleep(self.WaitTime)


class RepeatAlpha(Protocol):
  parameters = {
    "Channel": (0, "Channel to interact with"),
    "AlphaTau": (0.5e-3, "Alpha function tau"),
    "AlphaAmp": (19e-9, "Alpha function amplitude"),
    "LeadTime": (5e-3, "Alpha function delay"),
    "Dt": (50e-6, "Time between command points"),
    "Time": (15e-3, "Total command time"),
    "WaitTime": (0.5, "Time to wait between iterations")
  }
  def run(self):
    useCache = False
    while True:
      self.rtxi.checkEnd()
      num = int(self.Time/self.Dt)
      cmdList = functions.cmd(lambda t: self.AlphaAmp * functions.alpha(t-self.LeadTime, self.AlphaTau), num, self.Time)
      res = self.rtxi.runRtProgram(
        channel=self.Channel,
        mode="dc", 
        data=cmdList, 
        runTime=self.Time, 
        useMCCache=useCache, 
        interpolate=True, 
        fullInfo=False
      )
      self.rtxi.plot(res)
      useCache = True
      time.sleep(self.WaitTime)



class CCIVCurve(Protocol):
  parameters = {
    "Channel": (0, "Channel to interact with"),
    'IMax': (0.5e-9, "Maximum current"), 
    'IMin': (-0.5e-9, "Minimum current"), 
    'ISteps': (30, "Number of steps from Imin to Imax"),
    'LeadTime': (5e-3, "Time before starting pulse"),
    'PulseLength': (0.1, "Length of current pulse"),
    'LagTime': (50e-3, "Time to continue recording after pulse ends"),
    'WaitTime': (0.5, "Time to wait between iterations"),
    'WindowStart': (0.06, "Time after beginning of pulse to start measuring voltage"),
    'WindowEnd': (0.09, "Time after beginning of pulse to stop measuring voltage")
  }
  
  def run(self):
    ## initialize a MetaArray object for the raw data and IV curve
    ivCurve = MetaArray((3, self.ISteps), info=[{'cols': [
      {'name': 'current', 'units': 'A'}, 
      {'name': 'mean voltage', 'units': 'V'},
      {'name': 'max voltage', 'units': 'V'}
    ]}, {'name': 'Trial'}])
    
    traces = []
    rawDm = self.dm.createDir('raw')
    
    
    current = self.IMin
    dI = (self.IMax - self.IMin) / (self.ISteps-1)
    
    for i in range(0, self.ISteps):
      ## See if a stop has been requested
      self.rtxi.checkEnd()
      
      ## Prepare the current commands and run the program
      cmd = [(0.0, 0.0), (self.LeadTime, current), (self.LeadTime+self.PulseLength, 0.0)]
      result = self.rtxi.runRtProgram(
        channel=self.Channel,
        mode="ic",
        data=cmd,
        runTime=self.LeadTime+self.PulseLength+self.LagTime, 
        useMCCache=(i!=0), 
        interpolate=False
      )
      
      #self.rtxi.logMsg("IVCurve Protocol ran a trial")
      ## Read the results, append to raw data set
      self.rawDm.writeFile(result, "I=%g" % current, {'Current': current})
      traces.append(result)
      
      ## Select out records between 60ms and 100ms
      #sel = filter(lambda x: (x['time'] > WindowStart+lag and x['time'] < WindowEnd+lag), result)
      selWindow = (result['Time'] > self.WindowStart+self.LeadTime) * (result['Time'] < self.WindowEnd+self.LeadTime)
      sel = result[:, selWindow]
      
      ## Calculate the average voltage response and add to the IV curve array
      avg = mean(sel['Inp0'])
      if current > 0:
        maxVal = result['Inp0'].max()
      else:
        maxVal = result['Inp0'].min()
      ivCurve[:, i] = [current, avg, maxVal]
      
      #self.rtxi.plot(result)
      current += dI
      time.sleep(self.WaitTime)
    self.ivCurve = ivCurve
    self.traces = traces
    self.dm.writeFile(ivCurve, "ivCurve", info={'Description': "Current Clamp I/V Profile"})
    self.dm.logMsg("IVCurve Protocol is Complete")  
    #return (ivCurve, traces)
  
  def getFirstSpike(self):
    pass
  
  
  def showResults(self):
    pass
    

#class VCIVCurve(Protocol):
  #def __init__(self, dm=None, rtxi=None):
    #Protocol.__init__(self, dm, rtxi)
  #def run(self):
    #pass
  
  #def showResults(self):
    #pass

#class VCCapacitance(Protocol):
  #def __init__(self, dm=None, rtxi=None):
    #Protocol.__init__(self, dm, rtxi)
  #def run(self):
    #pass
  
  #def showResults(self):
    #pass

#class ElectrotonicStructure(Protocol):
  #def __init__(self, dm=None, rtxi=None):
    #Protocol.__init__(self, dm, rtxi)
  #def run(self):
    #pass
  
  #def showResults(self):
    #pass

#class AlphaThreshold(Protocol):
  #def __init__(self, dm=None, rtxi=None):
    #Protocol.__init__(self, dm, rtxi)
    #self.parameters = [
      #('Std.GThresh.Gmax', 10.e-9), ('Std.GThresh.Gmin', 0.0),
      #('Std.GThresh.Tau', 0.5e-3),
      #('Std.GThresh.iterations', 3.0, "Number of adaptive iterations to perform while searching for conductance threshold"),
      #('Std.GThresh.repetitions', 6.0, "Number of measurements to take for a single conductance."),
    #]
  
  #def run(self):
    #pass
  
  #def showResults(self):
    #pass












#class StdProto:
  #"""Class that runs standard protocols"""
  #params = {}
  #results = {}
  #filePrefix = ""
  #rtxi = None
  #apTemplate = None


  #def __init__(self, r, channel=0):
    #self.channel = channel
    #self.rtxi = r
    #self.rtxi.registerParams([
### parameters for the standard IV protocol
      #('Std.IVProf.Imax', 0.5e-9, "Maximum current"), 
      #('Std.IVProf.Imin', -0.5e-9, "Minimum current"), 
      #('Std.IVProf.Isteps', 30, "Number of steps from Imin to Imax"),
      #('Std.IVProf.PulseLength', 0.1, "Length of current pulse"),
      #('Std.IVProf.RestLength', 0.5, "Minimum time to wait between pulses"),
      #('Std.IVProf.WindowStart', 0.06, "Time after beginning of pulse to start measuring voltage"),
      #('Std.IVProf.WindowEnd', 0.09, "Time after beginning of pulse to stop measuring voltage")
    #])
    #self.rtxi.registerCallback("Measure IV Curve", self.measureIVCurve)
    
### parameters for the detection of conductance threshold for alpha waveform      
    #self.rtxi.registerParams([
      #('Std.GThresh.Gmax', 10.e-9), ('Std.GThresh.Gmin', 0.0),
      #('Std.GThresh.Tau', 0.5e-3),
      #('Std.GThresh.iterations', 3.0, "Number of adaptive iterations to perform while searching for conductance threshold"),
      #('Std.GThresh.repetitions', 6.0, "Number of measurements to take for a single conductance."),
### parameters for action potential detection
      #('Std.APDetect.minV', -20e-3, "Action potential detected when V goes from minV to maxV in less than maxDt"), 
      #('Std.APDetect.maxV', 0.0, "Action potential detected when V goes from minV to maxV in less than maxDt"), 
      #('Std.APDetect.maxDt', 2e-3, "Action potential detected when V goes from minV to maxV in less than maxDt"), 
    #])
    #self.rtxi.registerCallback("Measure GThresh", self.measureGThreshold)
    
    #self.rtxi.registerParams([
### parameters for the "hyp" protocol
      #('Std.HypProf.IPremax', 0.1e-9, "Maximum pre current"), 
      #('Std.HypProf.IPremin', -0.5e-9, "Minimum pre current"), 
      #('Std.HypProf.IPresteps', 10, "Number of steps from Imin to Imax"),
      #('Std.HypProf.PrePulseLength', 0.1, "Length of Pre current pulse"),
      #('Std.HypProf.ITestmax', 0.5e-9, "Maximum Test current"), 
      #('Std.HypProf.ITestmin', 0.1e-9, "Minimum Test current"), 
      #('Std.HypProf.ITeststeps', 2, "Number of steps from Imin to Imax"),
      #('Std.HypProf.TestPulseLength', 0.3, "Length of test current pulse"),
      #('Std.HypProf.RestLength', 1, "Minimum time to wait between pulses"),
      #('Std.HypProf.WindowStart', 0.06, "Time after beginning of pulse to start measuring voltage"),
      #('Std.HypProf.WindowEnd', 0.09, "Time after beginning of pulse to stop measuring voltage"),
      #('Std.HypProf.Nreps', 4, "Number of trials per current level")
    #])
    #self.rtxi.registerCallback("Measure Hyp Curve", self.measureHypCurve)
    
    #self.rtxi.registerParams([
      #("Std.repeatAlpha.alphaTau", 0.5e-3, "Alpha function tau"),
      #("Std.repeatAlpha.alphaAmp", 19e-9, "Alpha function amplitude"),
      #("Std.repeatAlpha.alphaDelay", 5e-3, "Alpha function delay"),
      #("Std.repeatAlpha.dt", 50e-6, "Time between command points"),
      #("Std.repeatAlpha.time", 15e-3, "Total command time"),
      #("Std.repeatAlpha.wait", 0.5, "Time between pulses")
    #])
    #self.rtxi.registerCallback("Repeat alpha", self.repeatAlpha)
    
    #self.rtxi.registerParams([
      #("Std.patchPulse.amplitude", -50e-12, "Square pulse amplitude"),
      #("Std.patchPulse.pulseWidth", 100e-3, "Square pulse duration"),
      #("Std.patchPulse.delay", 5e-3, "Delay to pulse start"),
      #("Std.patchPulse.time", 125e-3, "Total command time"),
      #("Std.patchPulse.wait", 200e-3, "Time between pulses")
    #])
    #self.rtxi.registerCallback("Patch pulse", self.patchPulse)
    
    #self.rtxi.registerParams([
      #("Std.scope.duration", 0.1, "Length of data to record"),
      #("Std.scope.wait", 0.0, "Time to wait between recordings")
    #])
    #self.rtxi.registerCallback("Scope", self.scope)
 
  #def setAPTemplate(self, temp):
    #self.apTemplate = temp
 
  ## Repeatedly record and plot results
  #def scope(self):
    #while( not self.rtxi.checkEnd() ):
      #recTime = self.rtxi.getParam("Std.scope.duration")
      #waitTime = self.rtxi.getParam("Std.scope.wait")
      #rec = self.rtxi.runRtProgram(channel=self.channel, mode="i=0", runTime=recTime, useMCCache=True, fullInfo=False)
      #self.rtxi.plot(rec)
      #time.sleep(waitTime);

  ## Repeatedly stimulates with alpha conductance and plots results
  #def repeatAlpha(self):
    #while( not self.rtxi.checkEnd() ):
      #tau = self.rtxi.getParam("Std.repeatAlpha.alphaTau")
      #amp = self.rtxi.getParam("Std.repeatAlpha.alphaAmp")
      #toff = self.rtxi.getParam("Std.repeatAlpha.alphaDelay")
      #dt = self.rtxi.getParam("Std.repeatAlpha.dt")
      #runTime = self.rtxi.getParam("Std.repeatAlpha.time")
      #wait = self.rtxi.getParam("Std.repeatAlpha.wait")
      
      #num = int(runTime/dt)
      #cmdList = cmd(lambda t: amp * alpha(t-toff, tau), num, runTime)
      #res = self.rtxi.runRtProgram(mode="dc", data=cmdList, runTime=runTime, channel=self.channel, useMCCache=True, interpolate=True, fullInfo=False)
      #self.rtxi.plot(res)
      #time.sleep(wait)
      
  ## Repeatedly stimulate with current step, plot results
  #def patchPulse(self):
    #while( not self.rtxi.checkEnd() ):
      #amp = self.rtxi.getParam("Std.patchPulse.amplitude")
      #pulseWidth = self.rtxi.getParam("Std.patchPulse.pulseWidth")
      #delay = self.rtxi.getParam("Std.patchPulse.delay")
      #cmdTime = self.rtxi.getParam("Std.patchPulse.time")
      #waitTime = self.rtxi.getParam("Std.patchPulse.wait")
      
      #cmd = [[0.0, 0.0], [delay, amp], [delay+pulseWidth, 0.0]]
      #res = self.rtxi.runRtProgram("ic", cmd, cmdTime, channel=self.channel, useMCCache=True, fullInfo=False)
      #self.rtxi.plot(res)
      
      #time.sleep(waitTime)
      
  #def measureCapacitance(self):
    #"""Generate a square wave current clamp signal and measure change in dV/dt.""" 
    ### Typical cell capacitance is around 10pF (?)
    #cycles=10
    #dt = 10e-3
    #di = 10e-11
    #t = 0.01
    #cmd = [[0., 0.]]
    
    #for i in range(0, cycles):
      #cmd.append([t, -di*0.5])
      #cmd.append([t+dt*0.5, di*0.5])
      #t += dt
    #cmd.append([t, 0.0])
    #data = self.rtxi.runRtProgram(channel=self.channel, mode='ic', data=cmd, runTime=t+0.01) 
    #try:
      #self.rtxi.mc.setMode(self.channel, 'i=0')
    #except:
      #pass
    #self.rtxi.plot(data)
    ### Do analysis here..
    
  #def findSpikes(self, data):
    #if self.apTemplate is None:
      #raise Exception("No action potential template defined, can not detect spikes.")
    #return fastRmsMatch(self.apTemplate['Inp0'], data['Inp0'])
    
  #def checkRestProperties(self, time=3.0, name=None, dirName=None):
    #"""Do an i=0 recording to determine resting membrane potential, stability, and spontaneous rate."""
    
    #data = self.rtxi.runRtProgram(channel=self.channel, mode='i=0', runTime=time)
    ### Remove first 1sec of recording
    #data = data[:, data['Time'] > 1.0]
    
    #if name is not None:
      #self.rtxi.writeFile(data, 'data_'+name, 'Cell health data '+name, dirName=dirName)
    
    #apd_minV = self.rtxi.getParam("Std.APDetect.minV")
    #apd_maxV = self.rtxi.getParam("Std.APDetect.maxV")
    #apd_maxDt = self.rtxi.getParam("Std.APDetect.maxDt")
    
    ### find action potentials
    ##aps = findActionPots(data, apd_minV, apd_maxV, apd_maxDt)
    #aps = self.findSpikes(data)
    
    ### generate a mask that is all True
    #times = data['Time'].view(ndarray)
    #restMask = times > -1.
    
    ### Remove sections of mask before and after spikes
    #for ap in aps:
      #t = times[ap]
      ### areas 5ms before and 100ms after a spike are removed
      #area = (times > t-5e-3) * (times < t+100e-3)
      #restMask -= area
      
    #restData = data[:, restMask]
    
    #restPot = mean(restData['Inp0'])
    #restPotDev = float(std(restData['Inp0']))
    #length = times[-1] - times[0]
    #apPerSec = len(aps) / length
    
    #return (restPot, restPotDev, apPerSec) 
    
    
  #def characterizeCell(self, name=""):
    #"""Runs measureIVCurve and measureGThreshold, stores results in self..cellData"""
    
    #self.cellData = {}
    #self.rtxi.logMsg("Measuring I/V profile..")
    #(self.cellData['ivc'], traces) = self.measureIVCurve(name)
    #if self.rtxi.checkEnd():
      #return;
    #self.rtxi.logMsg("Generating spike template from IV data...")
    #ap = getSpikeTemplate(self.cellData['ivc'], traces)
    #self.setAPTemplate(ap)
    #self.rtxi.writeFile(ap, "APTemplate", desc="action potential template")
    
    #self.rtxi.logMsg("Measuring conductance threshold..")
    #self.cellData['ct'] = self.measureGThreshold(name)
    #return self.cellData
  
  
  #def measureIVCurve(self, name=""):
    #"""Generates a series of current pulses and characterizes the voltage response"""
    
    #Imin = self.rtxi.getParam("Std.IVProf.Imin")
    #Imax = self.rtxi.getParam("Std.IVProf.Imax")
    #Isteps = int(self.rtxi.getParam("Std.IVProf.Isteps"))
    #PulseLen = self.rtxi.getParam("Std.IVProf.PulseLength")
    #RestLen = self.rtxi.getParam("Std.IVProf.RestLength")
    #WindowStart = self.rtxi.getParam("Std.IVProf.WindowStart")
    #WindowEnd = self.rtxi.getParam("Std.IVProf.WindowEnd")
    #lag = 5e-3
    
    #current = Imin
    #cStep = (Imax - Imin) / (float)(Isteps-1)
    
    ### initialize a MetaArray object for the raw data and IV curve
    #ivCurve = MetaArray((3, Isteps), info=[{'cols': [
      #{'name': 'current', 'units': 'A'}, 
      #{'name': 'mean voltage', 'units': 'V'},
      #{'name': 'max voltage', 'units': 'V'}
    #]}, {'name': 'Trial'}])
    #traces = []
    
    #for i in range(0, Isteps):
      ### See if a stop has been requested
      #if self.rtxi.checkEnd():
        #return;
      
      ### Prepare the current commands and run the program
      #cmd = [(0.0, 0.0), (lag, current), (PulseLen+lag, 0.0)]
      #result = self.rtxi.runRtProgram(mode="ic", data=cmd, runTime=lag+PulseLen+50e-3, channel=self.channel, useMCCache=True, interpolate=False)
      
      ##self.rtxi.logMsg("IVCurve Protocol ran a trial")
      ### Read the results, append to raw data set
      #self.rtxi.writeFile(result, "raw_I=%g" % current, desc=None, dirName="IV_Curve"+name)
      #traces.append(result)
      
      ### Select out records between 60ms and 100ms
      ##sel = filter(lambda x: (x['time'] > WindowStart+lag and x['time'] < WindowEnd+lag), result)
      #selWindow = (result['Time'] > WindowStart+lag) * (result['Time'] < WindowEnd+lag)
      #sel = result[:, selWindow]
      
      ### Calculate the average voltage response and add to the IV curve array
      #avg = mean(sel['Inp0'])
      #if current > 0:
        #maxVal = result['Inp0'].max()
      #else:
        #maxVal = result['Inp0'].min()
      #ivCurve[:, i] = [current, avg, maxVal]
      
      #self.rtxi.plot(result)
      #current += cStep
      #time.sleep(RestLen);
    #self.results['ivCurve'] = ivCurve
    #self.rtxi.writeFile(ivCurve, "ivc", desc="I/V profile", dirName="IV_Curve"+name)
    #self.rtxi.logMsg("IVCurve Protocol is Complete")  
    #return (ivCurve, traces)
  
  ### Generates current pulses for the hyp protocol and characterizes the voltage response
  #def measureHypCurve(self):
    #IPremin = self.rtxi.getParam("Std.HypProf.IPremin")
    #IPremax = self.rtxi.getParam("Std.HypProf.IPremax")
    #IPresteps = int(self.rtxi.getParam("Std.HypProf.IPresteps"))
    #tPrePulseLen = self.rtxi.getParam("Std.HypProf.PrePulseLength")
    #ITestmin = self.rtxi.getParam("Std.HypProf.ITestmin")
    #ITestmax = self.rtxi.getParam("Std.HypProf.ITestmax")
    #ITeststeps = int(self.rtxi.getParam("Std.HypProf.ITeststeps"))
    #tTestPulseLen = self.rtxi.getParam("Std.HypProf.TestPulseLength")
    #RestLen = self.rtxi.getParam("Std.HypProf.RestLength")
  ###    WindowStart = self.rtxi.getParam("Std.HypProf.WindowStart")
  ###    WindowEnd = self.rtxi.getParam("Std.HypProf.WindowEnd")
    #INreps = int(self.rtxi.getParam("Std.HypProf.Nreps"))
    #lag = 10e-3
    
    #precurrent = IPremin
    #cPreStep = 0.0
    #if IPresteps > 1 :
        #cPreStep = (IPremax - IPremin) / (float)(IPresteps-1)
    #testcurrent = ITestmin
    #cTestStep = 0.0
    #if ITeststeps > 1 :
        #cTestStep = (ITestmax - ITestmin) / (float)(ITeststeps-1)

    
    ### initialize a DataSet object for the raw data and IV curve
    #hypCurve = DataSet(names = ['current', 'mean voltage', 'max voltage'], units = ['A', 'V', 'V'], axes = ['x', 'y', 'y'])
    
    #for i in range(0, IPresteps):
      #for j in range(0, ITeststeps): ## See if a stop has been requested
        #for k in range(0, INreps): ## number of times for each one
            #if self.rtxi.checkEnd():
                #return;
        
            ### Prepare the current commands and run the program
            #cmd = [(0.0, 0.0), (lag, precurrent), (tPrePulseLen+lag, testcurrent), (tPrePulseLen+tTestPulseLen+lag, 0)]
            #result = self.rtxi.runRtProgram("ic", cmd, lag+tPrePulseLen+tTestPulseLen+50e-3, channel=self.channel)
            
            ### Read the results, append to raw data set
            #self.rtxi.writeFile(result, "raw_I=%g" % precurrent, desc=None, dirName="Hyp_Curve")
            
            ### Select out records between during last 10 msec of the prepulse
            #sel = filter(lambda x: (x['time'] > (tPrePulseLen+lag-10) and x['time'] < (tPrePulseLen+lag)), result)
            
            ### Calculate the average voltage response and add to the Hyp curve DataSet
            #avg = mean([x['Inp0'] for x in sel])
            #if precurrent > 0:
                #maxVal = max(result['Inp0'])
            #else:
                #maxVal = min(result['Inp0'])
            #hypCurve.append([precurrent, avg, maxVal])
            #self.rtxi.plot(result)
            ### if len(hypCurve) > 1:
            ###    self.rtxi.plot(hypCurve)
            
            #if j == 0:
                #precurrent += cPreStep
                #testcurrent = ITestmin
            #else:
                #testcurrent  += cTestStep
        
            #time.sleep(RestLen);
            ##self.rtxi.writeFile(rawData, "ivc_raw", "I/V profile raw data")
            #self.rtxi.writeFile(hypCurve, "hypc", desc="Hyp profile", dirName="Hyp_Curve")
##            self.rtxi.logMsg("Wrote file")
            #self.results['hypCurve'] = hypCurve
    #self.rtxi.logMsg("Hyp Protocol is Complete")
  
    
  #def measureGThreshold(self, name=""):
    #"""Generates a series of conductance pulses and finds the threshold for firing. Uses adaptive sampling to find best threshold."""
    
    #Gmin = self.rtxi.getParam("Std.GThresh.Gmin")
    #Gmax = self.rtxi.getParam("Std.GThresh.Gmax")
    #Tau = self.rtxi.getParam("Std.GThresh.Tau")
    #iters = int(self.rtxi.getParam("Std.GThresh.iterations"))
    #repPerPt = int(self.rtxi.getParam("Std.GThresh.repetitions"))
    #stepsPerIter = 2
    
    ### Load action potential detection parameters
    #apd_minV = self.rtxi.getParam("Std.APDetect.minV")
    #apd_maxV = self.rtxi.getParam("Std.APDetect.maxV")
    #apd_maxDt = self.rtxi.getParam("Std.APDetect.maxDt")
    
    ### Initialize G/V curve
    #gvCurve = MetaArray((2,0), info=[axis(cols=[('conductance', 'S'), ('frac actions', '')])])
    
    ### Each iteration is a full sweep of conductance checks from Gmin to Gmax
    #thresh = None
    #for it in range(0, iters):
      #steps = stepsPerIter*(it+2)
      #dG = (Gmax - Gmin) / (steps-1)
      #G = Gmin
      
      #for i in range(0, steps):
        ### Run multiple checks at this conductance, average results
        #percent = self.measureAlphaResponse(G, Tau, repPerPt, (apd_minV, apd_maxV, apd_maxDt), name)
        
        #if self.rtxi.checkEnd():
          #return;
        
        ### Collect, sort, and plot current G/V curve
        #gvCurve = gvCurve.append([G, percent], axis=1)
        #gvCurve = gvCurve.rowsort(axis=1, key='conductance')
        #if len(gvCurve) > 1:
          #self.rtxi.plot(gvCurve)
        #G += dG
      
      ### Determine where "interesting" region is in the G/V curve
      #v, status = fitSigmoid(gvCurve['conductance'], gvCurve['frac actions'], [1e9, 0.0])
      #thresh = v[1]
      ##if status != 1:
        ##raise Exception("Could not fit conductance profile to sigmoid!")
      
      #c1 = (-log(1./0.01 - 1.0) / v[0]) + v[1]
      #c2 = (-log(1./0.99 - 1.0) / v[0]) + v[1]
      #if c2 < c1 or c2 > 1e-7:
        #raise Exception("Sigmoid fit returned unusable results: %g - %g" % (c1, c2))
      #print "Next iteration: %g - %g" % (c1, c2)
      ##percent = gvCurve['frac actions']
      ##startInd = None
      ##stopInd = None
      ##for i in range(0, len(percent)):
        ##if percent[i] < 0.25:
          ##startInd = i
        ##if stopInd is None and percent[i] > 0.75:
          ##stopInd = i
      
      #steps += stepsPerIter
      
      ### Set up parameters for next iteration
      ##Gmin = max(0.0, gvCurve['conductance'][max(0, startInd)])
      ##Gmax = gvCurve['conductance'][min(len(percent)-1, stopInd)]
      #Gmin = max(0.0, c1)
      #Gmax = c2
      #dG = (Gmax - Gmin)/(steps+1)
      #Gmin -= dG
      #Gmax += dG
      #dG = (Gmax - Gmin)/(steps+1)
      ##if startInd is None or stopInd is None or startInd > stopInd:
        ##raise Exception("Could not detect conductance threshold!")
      ##print "Next iteration: %d-%d  %g - %g" % (startInd, stopInd, Gmin, Gmax)
      
    ### Write store results, 
    #self.rtxi.writeFile(gvCurve, "gvc", desc="conductance threshold profile", dirName="GThresh"+name)
    #self.results['gvCurve'] = gvCurve
    
    ### determine the conductance threshold from the G/V curve
    ##data = gvCurve[['conductance', 'frac actions']]
    ##thresh = triggers(data, 0.5)
    ##if( len(thresh) < 1 ):
      ##self.rtxi.logMsg("<warning>Could not find conductance threshold for this cell!</warning>")
    ##elif len(thresh) > 1:
      ##self.results['gThreshold'] = thresh[-1]
    ##else:
    #self.results['gThreshold'] = thresh
    
  
  #def measureAlphaResponse(self, amplitude, tau, n, apd=None, name=""):
    #"""Generate alpha conductance waveforms and measure resulting action potentials."""
    
    ##maxv = []
    #percent = []
    #data = []
    #now = time.time()
    
    #cmd = self.genCmd(lambda t: amplitude * alpha(t-5e-3, tau), tau*20.+5e-3, 8.0)
    #for i in range(0, n):
      #result = self.rtxi.runRtProgram(mode="dc", data=cmd, runTime=tau*20.+5e-3, channel=self.channel, useMCCache=True, interpolate=True)
      #mark = time.time()
      
      #self.rtxi.plot(result)
      #data.append(result)
      ##maxv.append(maxDenoise(result['Inp0'].view(ndarray), 2))
      #nap = len(fastRmsMatch(self.apTemplate['Inp0'], result['Inp0']))
      ##if apd != None and len(apd) == 3:
        ##nap = len(findActionPots(result[['Time', 'Inp0']], apd[0], apd[1], apd[2]))
      ##else:
        ##nap = len(findActionPots(result[['Time', 'Inp0']]))
      #percent.append(nap)
      #if self.rtxi.checkEnd():
        #return;
      
      #time.sleep(max(0.0, 0.15-(time.time()-mark)))
    #allData = MetaArray(hstack(data), info=data[0].infoCopy())
    #self.rtxi.writeFile(allData, "raw_G=%g" % amplitude, dirName="GThresh"+name, desc=None)
    #return mean(percent)
    
  #def genCmd(self, func, length, superSample = 1.0):
    #"""Generate list which can be used as the data parameter for rtxi.runRtProgram(...)"""
    
    #period = self.rtxi.getPeriod()
    #numPts = int(length / period * superSample);
    #cmd = []
    #for i in range(0, numPts):
      #t = float(i)/float(numPts)*length
      #cmd.append((t, func(t)))
    #return cmd

    
    
    
    
    
    
    
    
#class IVCurve(SequenceRunner):
  #def __init__(self, opts, dirName, rtxi=None, channel=0):
    ### Make sure we call the superclass's init function
    #SequenceRunner.init(self, 1)
    
    #self.channel = channel
    
    ### Options are pulled from the rtxi parameter list by default, but can be overridden.
    #self.optList = ['Imin', 'Imax', 'Isteps', 'PulseLength', 'RestLength', 'WindowStart', 'WindowEnd']
    #for o in self.optList:
      #if not opts.has_key(o):
        #opts[o] = rtxi.getParam("Std.IVProf." + o)
    #self.opts = opts
    #self.opts['lead'] = 5e-3  ## extra time at the beginning of each trace
    #self.opts['lag'] = 50e-3  ## extra time at the end of each trace
    
    ### Define parameters to iterate over
    #self.setParameterSpace({'current': floatSpace(opts['Imin'], opts['Imax'], opts['Isteps'])})
    #self.setAxisOrder(['current'])
    
    ### initialize a MetaArray object for the IV curve
    #self.ivCurve = MetaArray((3, Isteps), info=[{'cols': [
      #{'name': 'current', 'units': 'A'}, 
      #{'name': 'mean voltage', 'units': 'V'},
      #{'name': 'max voltage', 'units': 'V'}
    #]}, {'name': 'Trial'}, self.opts])
  
  
  #def execute(self, ind):
    ### Get the current level for this iteration
    #params = self.getParams(ind)
    #current = params['current']
    
    ### See if a stop has been requested
    #if self.rtxi.checkEnd():
      ## this exception tells the recursive loop to exit from all levels
      #raise Exception('break', 0)
    
    ### Prepare the current commands and run the program
    #lead = self.opts['lead']
    #lag = self.opts['lag']
    #plen = self.opts['PulseLength']
    #cmd = [(0.0, 0.0), (lead, current), (plen + lead, 0.0)]
    #result = self.rtxi.runRtProgram(mode="ic", data=cmd, runTime=lead+plen+lag, channel=self.channel, useMCCache=True, interpolate=False)
    #doneTime = time.time()
    
    ### Read the results, append to raw data set
    #self.rtxi.writeFile(result, self.getIterName(ind), desc=None, dirName=self.dirName + '/raw')
    
    ### Select out records between meanStart and meanStop
    #selWindow = (result['Time'] > self.opts['WindowStart']+lead) * (result['Time'] < self.opts['WindowStop']+lead)
    #sel = result[:, selWindow]
    
    ### Calculate the average voltage response and add to the IV curve array
    #avg = mean(sel['Inp0'])
    #if current > 0:
      #maxVal = result['Inp0'].max()
    #else:
      #maxVal = result['Inp0'].min()
    #self.ivCurve[:, i] = [current, avg, maxVal]
    
    #self.rtxi.plot(result)
    #time.sleep(max(0.0, self.opts['RestLen']+doneTime-time.time()))






#class GThreshold(SequenceRunner):
  #def __init__(self, opts, dirName, rtxi=None, channel=0):
    ### Make sure we call the superclass's init function
    #SequenceRunner.init(self, 1)
    
    #self.channel = channel
    
    ### Options are pulled from the rtxi parameter list by default, but can be overridden.
    #self.optList = ['Tau', 'Gmin', 'Gmax', 'Gsteps']
    #for o in self.optList:
      #if not opts.has_key(o):
        #opts[o] = rtxi.getParam("Std.GThresh." + o)
    #self.opts = opts
    #self.opts['lead'] = 5e-3  ## extra time at the beginning of each trace
    #self.opts['length'] = self.opts['Tau'] * 10. + 10e-3 ## Time to record after start of alpha
    
    ### Define parameters to iterate over
    #self.setParameterSpace({'conductance': floatSpace(opts['Gmin'], opts['Gmax'], opts['Gsteps'])})
    #self.setAxisOrder(['conductance'])
    
    ### initialize a MetaArray object for the IV curve
    #self.ivCurve = MetaArray((3, Isteps), info=[{'cols': [
      #{'name': 'current', 'units': 'A'}, 
      #{'name': 'mean voltage', 'units': 'V'},
      #{'name': 'max voltage', 'units': 'V'}
    #]}, {'name': 'Trial'}, self.opts])
  
  
  #def execute(self, ind):
    ### Get the current level for this iteration
    #params = self.getParams(ind)
    #current = params['current']
    
    ### See if a stop has been requested
    #if self.rtxi.checkEnd():
      ## this exception tells the recursive loop to exit from all levels
      #raise Exception('break', 0)
    
    ### Prepare the current commands and run the program
    #lead = self.opts['lead']
    #lag = self.opts['lag']
    #plen = self.opts['PulseLength']
    #cmd = [(0.0, 0.0), (lead, current), (plen + lead, 0.0)]
    #result = self.rtxi.runRtProgram(mode="ic", data=cmd, runTime=lead+plen+lag, channel=self.channel, useMCCache=True, interpolate=False)
    #doneTime = time.time()
    
    ### Read the results, append to raw data set
    #self.rtxi.writeFile(result, self.getIterName(ind), desc=None, dirName=self.dirName + '/raw')
    
    ### Select out records between meanStart and meanStop
    #selWindow = (result['Time'] > self.opts['WindowStart']+lead) * (result['Time'] < self.opts['WindowStop']+lead)
    #sel = result[:, selWindow]
    
    ### Calculate the average voltage response and add to the IV curve array
    #avg = mean(sel['Inp0'])
    #if current > 0:
      #maxVal = result['Inp0'].max()
    #else:
      #maxVal = result['Inp0'].min()
    #self.ivCurve[:, i] = [current, avg, maxVal]
    
    #self.rtxi.plot(result)
    #time.sleep(max(0.0, self.opts['RestLen']+doneTime-time.time()))
    
