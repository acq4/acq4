class Protocol:
  """Abstract class for protocols. Derived classes should handle running the protocol, storing and analyzing data, and reloading data for re-analysis."""
  parameters = None
  instParams = None
  
  def __init__(self, name=None, dm=None, rtxi=None, params=None, prefix=None):
    if name is None:
      self.name = self.__class__.__name__
    else:
      self.name = name
    
    
    ## If RTXI is undefined, protocols can not be run.
    ## Pre-existing data can still be read and analyzed, though.
    self.rtxi = rtxi
    self.paramPrefix = prefix
    
    ## Store parameter values specific to this instance
    if params is None:
      self.instParams = {}
    else:
      self.instParams = params
    
    ## If DM is undefined, protocols will be run without storage
    self.baseDM = dm
    self.dm = None
    
  def getDM(self):
    if self.dm is None and self.baseDM is not None:
      self.dm = self.baseDM.mkdir(self.name, info={"ProtocolType": self.__class__.__name__})
    return self.dm
    
  def run(self):
    raise Exception("Protocol.run() must be redefined in a subclass.")
  
  def showResults(self):
    raise Exception("Protocol.showResults() must be redefined in a subclass.")

  def listParameters(self):
    return self.parameters
  
  def getParam(self, name):
    if self.instParams.has_key(name):
      return self.instParams[name]
    elif self.parameters.has_key(name):
      return self.rtxi.getParam(self.prefix() + name)
    else:
      raise Exception("Protocol has no parameter named '%s'" % name)

  def setParam(self, pName, value):
    self.instParams[pName] = value

  #def getParams(self, names):
    #p = {}
    #for n in names:
      #p[n] = self.getParam(n)
    #return p

  def __getattr__(self, name):
    return self.getParam(name)

  def prefix(self):
    if self.paramPrefix is None:
      return "Protocols." + self.name + "."
    else:
      return self.paramPrefix
  
  def register(self):
    self.rtxi.registerParams(self.parameters, prefix=self.prefix())
    
  def __repr__(self):
    return "<Protocol type: %s  name: %s>" % (self.__class__.__name__, self.name)