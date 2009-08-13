# -*- coding: utf-8 -*-
from MetaArray import *
from numpy import zeros

def runSequence(func, params, order, dtype=None, passHash=False):
    """Convenience function that iterates a function over a given parameter space, inserting the function's return value into an array"""
    seq = SequenceRunner(params, order, dtype=dtype, passHash=passHash)
    return seq.start(func)


class SequenceRunner:
    """Run a function multiple times with a sequence of parameters.
    Parameters are:
        params: List of parameters to be passed to kernel function
        order: list of parameter names in the order they should be iterated
        passHash: boolean value. If true, parameters are passed to the kernel function as a single hash.
                The default value is False; parameters are passed as normal named function arguments.
                            
    There are two ways to invoke a SequenceRunner object:
        obj.start(func) -- func will be the kernel function invoked by the SR object.
        obj.start() -- the SR object will invoke obj.execute as the kernel function (This function must be defined in a subclass). 
    """
  
    def __init__(self, params=None, order=None, dtype=None, passHash=False):
        self._params = params
        self._order = order
        self._endFuncs = []
        self._passHash = passHash
        self._dtype = dtype
  
    def setEndFuncs(self, funcs):
        self._endFuncs = funcs

    def setPassHash(self, b):
        self._passHash = b

    def setOrder(self, order):
        """Define the order in which axes are iterated over"""
        # TODO: allow grouping of axes  ie order=['t', ('x', 'y')]
        self._order = order
  
    def setParams(self, params):
        """Define the set of parameters to be passed to the kernel function. The setOrder function determines which parameters will be irerated over.
        Example: 
          setParameterSpace({'x': linspace(0.2, 0.8, 10), 't': logSpace(0.01, 1.0, 20), 'iter': arange(0, 10), 'option': 7})
        """
        if type(params) is not types.DictType:
            raise Exception("Parameter specification must be a dict like {'param_name': [params], ...}")
        self._params = params

    def execute(self, inds):
        """Function to be run for every iteration. Must accept a tuple of parameter indexes. 
        The function should make use of the following methods which may also be overridden:
            getParams -- Fetch parameter values from inds
            getShape -- Returns a tuple of the shape of the parameter space
            getIterName -- Generate a unique name for this iteration based on inds and the axis names"""
        raise Exception("execute function not defined for this sequence!")
  
    def start(self, func=None, returnMask=False):
        if func is None:
            func = self.execute
        self._return = None
        self._runMask = None
        
        self.makeParamSpace()
        
        ## Run parameter space recursive loop
        try:
            self.nloop(func=func)
        except Exception, e:
            ## If the loop exited due to a break command, that's fine.
            ## Otherwise, re-raise the exception
            if len(e.args) < 1 or e.args[0] != 'break':
                raise
        if returnMask:
            return (self._return, self._runMask)
        else:
            return self._return
    
    def nloop(self, ind=None, func=None):
        """Recursively loop over all points in the parameter space"""
        if ind is None:
            ind = []
        if len(ind) == len(self._order):
            params = self.getParams(ind)
            stop = False
            try:
                if self._passHash:
                    ret = func(params)
                else:
                    ret = func(**params)
            except Exception, e:
                if len(e.args) > 0 and e.args[0] == 'stop':
                    stop = True
                    if len(e.args) > 1:
                        ret = e.args[1]
                else:
                    raise
        
            if self._return is None:
                self.buildReturnArray(ret)
                
            self._return[tuple(ind)] = ret
            self._runMask[tuple(ind)] = True
            #print "--------"
            #print self._return
            if stop:
                raise Exception('break', len(ind))
            
        else:
            ax = self._order[len(ind)]
            params = self._paramSpace[ax]
            for i in range(0, len(params)):
                ind2 = ind + [i]
                try:
                    self.nloop(ind2, func=func)
                except Exception, e:
                    if e.args[0] == 'break':
                        if e.args[1] <= 1:
                            break
                        else:
                            raise Exception('break', e.args[1] - 1)
                    else:
                        raise
            self.runEndFunc(ind)
    
    def runEndFunc(self, ind):
        if len(self._endFuncs) > len(ind):
            f = self._endFuncs[len(ind)]
            if f is not None:
                f(ind)
    
    def getParams(self, ind):
        d = self._params.copy()
        for i in range(0, len(self._order)):
            pn = self._order[i]
            val = self._paramSpace[pn][ind[i]]
            if '[' in pn:
                name = pn[:pn.index('[')]
                pind = pn[pn.index('['):]
                exec('d[name]%s = val' % pind)
            else:
                d[pn] = val
        return d
        
    def makeParamSpace(self):
        """Parse the axis order specification in self._order and extract the lists of values to use in each axis"""
        self._paramSpace = {}
        for i in self._order:
            if '[' in i:
                name = i[:i.index('[')]
                ind = i[i.index('['):]
                params = eval('self._params["%s"]%s' % (name, ind))
            else:
                params = self._params[i]
                
            if type(params) not in (types.ListType, types.TupleType):
                params = [params]
            self._paramSpace[i] = params
        
    def buildReturnArray(self, ret):
        shape = tuple([len(self._paramSpace[p]) for p in self._order])
        
        shapeExtra = ()
        dtype = self._dtype
        if ndarray in type(ret).__bases__ or type(ret) is ndarray:
            if dtype is None:
                dtype = ret.dtype
            shapeExtra = ret.shape
        elif type(ret) is types.FloatType:
            dtype = float
        elif type(ret) is types.IntType:
            dtype = int
        else:
            dtype = object
            
        info = [{'name': p, 'values': self._paramSpace[p]} for p in self._order]
        self._return = MetaArray(zeros(shape + shapeExtra, dtype=dtype), info=info)
        self._runMask = MetaArray(zeros(shape, dtype=bool), info=info)
