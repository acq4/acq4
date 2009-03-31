import protocols, Protocol

class ProtocolRunner:
  def __init__(self, rtxi, dm=None, defaultChannel=0):
    self.rtxi = rtxi
    self.dm = dm
    self.defaultChannel = defaultChannel
    self.protos = {}
    
    ### Register parameters
    for pName in dir(protocols):
      obj = getattr(protocols, pName)
      if hasattr(obj, '__bases__') and Protocol.Protocol in obj.__bases__:
        proto = obj(rtxi=self.rtxi).register()
        self.rtxi.registerCallback(pName, self.runProtocol, pName, pName+"CB")
      
  
  def runProtocol(self, protoName, instanceName, *args):
    #if self.protos.has_key(instanceName):
      #raise Exception("Already ran protocol named '%s'" % instanceName)
    
    #if self.dm is None:
      #dm1 = None
    #else:
      #dm1 = self.dm.createSubdir(instanceName, info={"ProtocolType": protoName})
    
    if protoName in dir(protocols):
      protoCls = getattr(protocols, protoName)
      proto = protoCls(rtxi=self.rtxi, dm=dm, *args)
      self.protos[instanceName] = proto
    else:
      raise Exception("Can not find protocol named '%s'" % protoName)
    
    proto.run()
    return proto
  
  def getProtocol(self, name):
    if self.protos.has_key(name):
      return self.protos[name]
    else:
      raise Exception("Can not find protocol instance named '%s'" % pName)
  
  #def ivCurveCC(self, name):
    #pass
  
  #def ivCurveVC(self, name):
    #pass
  
  #def capacitance(self, name):
    #pass
  
  #def alphaThreshold(self, name):
    #pass
  
  