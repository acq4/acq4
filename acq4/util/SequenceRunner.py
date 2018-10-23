# -*- coding: utf-8 -*-
from __future__ import print_function
"""
SequenceRunner.py -  Used for running multi-dimensional for-loops
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from acq4.util.metaarray import *
import numpy as np

def runSequence(func, params, order, dtype=None, passArgs=False, linkedParams=None):
    """Convenience function that iterates a function over a given parameter space, inserting the function's return value into an array (see SequenceRunner for documentation)"""
    seq = SequenceRunner(params, order, dtype=dtype, passArgs=passArgs, linkedParams=linkedParams)
    return seq.start(func)


class SequenceRunner:
    """Run a function multiple times with a sequence of parameters. Think of it as a multi-dimensional for-loop.
    Parameters are:
        params: List of parameters to be passed to kernel function
        order: list of parameter names in the order they should be iterated
        passArgs: boolean. If False (default), parameters are passed to the kernel function as a single dict.
                If True, parameters are passed as normal named function arguments.
        linkedParams: Dictionary of parameters that should be iterated together
        
                            
    There are two ways to invoke a SequenceRunner object:
        obj.start(func) -- func will be the kernel function invoked by the SR object.
        obj.start() -- the SR object will invoke obj.execute as the kernel function (This function must be defined in a subclass). 
    """
  
    def __init__(self, params=None, order=None, dtype=None, passArgs=False, linkedParams=None):
        self._params = params
        self._linkedParams = linkedParams
        self._order = order
        self._endFuncs = []
        self._passArgs = passArgs
        self._dtype = dtype
  
    def setEndFuncs(self, funcs):
        self._endFuncs = funcs

    def setPassArgs(self, b):
        self._passArgs = b

    def setOrder(self, order):
        """Define the order in which axes are iterated over"""
        # TODO: allow grouping of axes  ie order=['t', ('x', 'y')]
        self._order = order
  
    def setParams(self, params):
        """Define the set of parameters to be passed to the kernel function. The setOrder function determines which parameters will be irerated over.
        Example: 
          setParameterSpace({'x': linspace(0.2, 0.8, 10), 't': logSpace(0.01, 1.0, 20), 'iter': arange(0, 10), 'option': 7})
        """
        if not isinstance(params, dict):
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
        except Exception as e:
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
                if self._passArgs:
                    ret = func(**params)
                else:
                    ret = func(params)
            except Exception as e:
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
            for i in range(len(params)):
                ind2 = ind + [i]
                try:
                    self.nloop(ind2, func=func)
                except Exception as e:
                    if len(e.args) > 0 and e.args[0] == 'break':
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
        
        ## Determine current value for each parameter
        for i in range(len(self._order)):
            pn = self._order[i]
            val = self._paramSpace[pn][ind[i]]
            if '[' in pn:
                name = pn[:pn.index('[')]
                pind = pn[pn.index('['):]
                exec('d[name]%s = val' % pind)
            else:
                d[pn] = val
                
            ## check for linked parameters
            if self._linkedParams is not None and pn in self._linkedParams:
                for lp in self._linkedParams[pn]:
                    d[lp] = val
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
                
            if not isinstance(params, (list, tuple)):
                params = [params]
            self._paramSpace[i] = params
        
    def buildReturnArray(self, ret):
        shape = tuple([len(self._paramSpace[p]) for p in self._order])
        
        shapeExtra = ()
        dtype = self._dtype
        if isinstance(ret, np.ndarray):
            if dtype is None:
                dtype = ret.dtype
            shapeExtra = ret.shape
        elif isinstance(ret, float):
            dtype = float
        elif isinstance(ret, int):
            dtype = int
        else:
            dtype = object
            
        info = [{'name': p, 'values': self._paramSpace[p]} for p in self._order]
        self._return = MetaArray(np.zeros(shape + shapeExtra, dtype=dtype), info=info)
        self._runMask = MetaArray(np.zeros(shape, dtype=bool), info=info)



if __name__ == '__main__':
    #!/usr/bin/python -i
    # -*- coding: utf-8 -*-
    #from SequenceRunner import *
    from numpy import *

    print("========== runSequence test: simplest way to invoke sequence ============")
    def fn(x, y):
        print(x, "*", y, "=", x*y)
        return x*y
    print(runSequence(fn, {'x': [1,3,5,7], 'y': [2,4,6,8]}, ['y', 'x'], passArgs=True))


    print("\n========== seq.start(fn) test: Sequence using reusable SR object ============")
    seq = SequenceRunner({'x': [1,3,5,7], 'y': [2,4,6,8]}, ['y', 'x'], passArgs=True)
    print(seq.start(fn))



    print("\n========== seq.start() test: Sequence using subclassed SR object ============")

    class SR(SequenceRunner):
        def execute(self, x, y, z):
            return x * y + z

    s = SR({'x': [1,3,5,7], 'y': [2,4,6,8], 'z': 0.5}, ['y', 'x'], passArgs=True)
    print(s.start())

    print("\n========== seq.start() 3D parameter space test ============")
    s.setParams({'x': [1,3,5,7], 'y': [2,4,6,8], 'z': [0.5, 0.6, 0.7]})
    s.setOrder(['x', 'z', 'y'])
    a = s.start()
    print(a)

    print("\n========== break test: kernel function may skip parts of the parameter space ============")
    s = SR({'x': [1,3,5,7,9,11,13], 'y': [2,4,6,8,10,12,14]}, ['x', 'y'], passArgs=True)
    def fn(x, y):
        prod = x * y
        if x > 7:
            raise Exception('break', 2)
        if prod > 60:
            raise Exception('break', 1)
        return prod
    print(s.start(fn, returnMask=True))


    print("\n========== line end test: functions run at specific edges of the parameter space ============")
    s = SR({'x': [1,3,5,7], 'y': [2,4,6,8]}, ['x', 'y'], passArgs=True)
    def fn(x, y):
        return x*y
    def fn2(ind):
        print("end of row", ind)
    s.setEndFuncs([None, fn2])
    s.start(fn)




    print("\n========== nested index test: specific parts of each parameter are flagged for iteration ============")
    def fn(x, y):
        print("x:", x, "   y:", y)
        return 0
    runSequence(fn, {'x': [1,3,[5,6,7],8], 'y': {'a': 1, 'b': [1,2,[3,'x',5],6]}}, ['y["b"][2]', 'x[2]'], passArgs=True)


    print("\n========== ndarray return test: kernel function returns an array, return is 2D array ============")
    def fn(tVals, yVals, nPts):
        """Generate a waveform n points long with steps defined by tVals and yVals"""
        arr = np.zeros((nPts))
        tVals.append(nPts)
        for i in range(len(yVals)):
            arr[tVals[i]:tVals[i+1]] = yVals[i]
        return arr
    print(runSequence(fn, {'nPts': 10, 'tVals': [0, 3, 8], 'yVals': [0, [-5, -2, 2, 5], 0]}, ['yVals[1]'], passArgs=True))
    