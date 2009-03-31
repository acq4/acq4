
def runSequence():
  """Convenience function that iterates a function over a given parameter space, inserting the function's return value into an array"""
  pass


class SequenceRunner:
  """Run a function multiple times with a sequence of parameters. This is an abstract class and must be subclassed to function properly.
  """
  
  def __init__(self, nDim=1, paramSpace=None, axisOrder=None):
    self.nDim = nDim
    self._params = paramSpace
    self._order = axisOrder
    #self.baseDir = baseDir
    #self.opts = opts
    self._endFuncs = []
    
  def setNDim(self, n):
    self._nDim = n
  def getNDim(self):
    return self._nDim
  nDim = property(getNDim, setNDim)
  
  
  def setEndFuncs(self, funcs):
    self._endFuncs = funcs
  
    
  def setAxisOrder(self, order):
    """Define the order in which axes are iterated over"""
    # TODO: allow grouping of axes 
    self._order = order
  
  def setParameterSpace(self, params):
    """Define the sequence of parameter values to iterate over for all axes in the parameter space.
    
    Example: 
      setParameterSpace({'x': linspace(0.2, 0.8, 10), 't': logSpace(0.01, 1.0, 20), 'iter': arange(0, 10)})
    """
    if type(params) is not types.DictType:
      raise Exception("Parameter specification must be a dict like {'param_name': [params], ...}")
    self._params = params

  def getIterName(self, ind):
    return '_'.join(["%s=%d" % (self._order[n], ind[n]) for n in range(0, len(ind))])

  def execute(self, inds):
    """Function to be run for every iteration. Must accept a tuple of parameter indexes. 
    
    The function should make use of the following methods which may also be overridden:
      getParams -- Fetch parameter values from inds
      getShape -- Returns a tuple of the shape of the parameter space
      getIterName -- Generate a unique name for this iteration based on inds and the axis names
      baseDir -- directory where data should be stored."""
    raise Exception("execute function not defined for this sequence!")
  
  def getParams(self, ind):
    """Given a list of indexes, return a list of the corresponding parameters."""
    #p = {}
    #for x in ind.keys():
      #p[x] = self._params[x][ind[x]]
    #return p
    return [self._params[self._order[n]][ind[n]] for n in range(0, len(ind))]
  
  def start(self):
    ## shape of parameter space
    pshape = tuple([len(self._params[x]) for x in self._order])
    
    ## Holder for iteration names
    #maxiter = {}
    #for n in self._order:
      #maxiter[n] = len(self._params[n])-1
    maxiter = [len(self._params[n])-1 for n in self._order]
    nameLen = len(self.getIterName(maxiter))
    info = [axis(name=n, values=self._params[n]) for n in self._order]
    self.names = MetaArray(pshape, dtype='|S%d' % nameLen, info=info)
    self.names[...] = ''
    
    ## Run parameter space recursive loop
    try:
      self.nloop(names=self.names)
    except Exception, e:
      ## If the loop exited due to a break command, that's fine.
      ## Otherwise, re-raise the exception
      if len(e.args) < 1 or e.args[0] != 'break':
        raise
    return self.names
    
  def nloop(self, ind=[], names=None):
    """Recursively loop over all points in the parameter space"""
    if len(ind) == len(self._order):
      ind = tuple(ind)
      self.execute(ind)
      if names is not None:
        names[ind] = self.getIterName(ind)
    else:
      ax = self._order[len(ind)]
      params = self._params[ax]
      for i in range(0, len(params)):
        ind2 = ind + [i]
        try:
          self.nloop(ind2, names)
        except Exception, e:
          if e.args[0] == 'break':
            if e.args[1] == 1:
              break
            else:
              raise Exception('break', e.args[1] - 1)
          
      self.runEndFunc(ind)
    
  def runEndFunc(self, ind):
    if len(self._endFuncs) > len(ind):
      self._endFuncs[len(ind)](ind)
    
  def indexDict(self, ind):
    d = {}
    for i in range(0, self.nDim):
      d[self._order[i]] = ind[i]
    return d
