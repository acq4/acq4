# -*- coding: utf-8 -*-
"""
MetaArray.py -  Class encapsulating ndarray with meta data
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

MetaArray is an extension of ndarray which allows storage of per-axis meta data
such as axis values, names, units, column names, etc. It also enables several
new methods for slicing and indexing the array based on this meta data. 
More info at http://www.scipy.org/Cookbook/MetaArray
"""


from numpy import ndarray, array, empty, fromstring, arange, concatenate
import types, copy, threading, os, re
import pickle
#import traceback


def axis(name=None, cols=None, values=None, units=None):
    """Convenience function for generating axis descriptions when defining MetaArrays"""
    ax = {}
    cNameOrder = ['name', 'units', 'title']
    if name is not None:
        ax['name'] = name
    if values is not None:
        ax['values'] = values
    if units is not None:
        ax['units'] = units
    if cols is not None:
        ax['cols'] = []
        for c in cols:
            if type(c) != types.ListType and type(c) != types.TupleType:
                c = [c]
            col = {}
            for i in range(0,len(c)):
                col[cNameOrder[i]] = c[i]
            ax['cols'].append(col)
    return ax




class MetaArray(ndarray):
    """N-dimensional array with meta data such as axis titles, units, and column names.
  
    May be initialized with a file name, a tuple representing the dimensions of the array,
    or any arguments that could be passed on to numpy.array()
  
    The info argument sets the metadata for the entire array. It is composed of a list
    of axis descriptions where each axis may have a name, title, units, and a list of column 
    descriptions. An additional dict at the end of the axis list may specify parameters
    that apply to values in the entire array.
  
    For example:
        A 2D array of altitude values for a topographical map might look like
            info=[
        {'name': 'lat', 'title': 'Lattitude'}, 
        {'name': 'lon', 'title': 'Longitude'}, 
        {'title': 'Altitude', 'units': 'm'}
      ]
        In this case, every value in the array represents the altitude in feet at the lat, lon
        position represented by the array index. All of the following return the 
        value at lat=10, lon=5:
            array[10, 5]
            array['lon':5, 'lat':10]
            array['lat':10][5]
        Now suppose we want to combine this data with another array of equal dimensions that
        represents the average rainfall for each location. We could easily store these as two 
        separate arrays or combine them into a 3D array with this description:
            info=[
        {'name': 'vals', 'cols': [
          {'name': 'altitude', 'units': 'm'}, 
          {'name': 'rainfall', 'units': 'cm/year'}
        ]},
        {'name': 'lat', 'title': 'Lattitude'}, 
        {'name': 'lon', 'title': 'Longitude'}
      ]
        We can now access the altitude values with array[0] or array['altitude'], and the
        rainfall values with array[1] or array['rainfall']. All of the following return
        the rainfall value at lat=10, lon=5:
            array[1, 10, 5]
            array['lon':5, 'lat':10, 'val': 'rainfall']
            array['rainfall', 'lon':5, 'lat':10]
        Notice that in the second example, there is no need for an extra (4th) axis description
        since the actual values are described (name and units) in the column info for the first axis.
    """
  
    version = '2'
    
    ## Types allowed as axis or column names
    nameTypes = [basestring, tuple]
    @staticmethod
    def isNameType(var):
        return any([isinstance(var, t) for t in MetaArray.nameTypes])
  
    def __new__(subtype, data=None, file=None, info=None, dtype=None, copy=False):
        if data is not None:
            if type(data) is types.TupleType:
                subarr = empty(data, dtype=dtype)
            else:
                subarr = array(data, dtype=dtype, copy=copy)
            subarr = subarr.view(subtype)

            if info is not None:
                try:
                    info = list(info)
                except:
                    raise Exception("Info must be a list of axis specifications")
                if len(info) < subarr.ndim+1:
                    info.extend([{}]*(subarr.ndim+1-len(info)))
                elif len(info) > subarr.ndim+1:
                    raise Exception("Info parameter must be list of length ndim+1 or less.")
                for i in range(0,len(info)):
                    if type(info[i]) != types.DictType:
                        if info[i] is None:
                            info[i] = {}
                        else:
                            raise Exception("Axis specification must be Dict or None")
                    if info[i].has_key('values'):
                        if type(info[i]['values']) is types.ListType:
                            info[i]['values'] = array(info[i]['values'])
                        elif type(info[i]['values']) is not ndarray:
                            raise Exception("Axis values must be specified as list or ndarray")
                subarr._info = info
            elif hasattr(data, '_info'):
                subarr._info = data._info

        elif file is not None:
            fd = open(file, 'rb')
            meta = MetaArray._readMeta(fd)
            if 'version' in meta:
                ver = meta['version']
            else:
                ver = 1
            rFuncName = '_readData%s' % str(ver)
            if not hasattr(MetaArray, rFuncName):
                raise Exception("This MetaArray library does not support array version '%s'" % ver)
            rFunc = getattr(MetaArray, rFuncName)
            subarr = rFunc(fd, meta, subtype)
                

        return subarr


    def __array_finalize__(self,obj):
        # We use the getattr method to set a default if 'obj' doesn't have the 'info' attribute
        self._info = getattr(obj, 'info', [{}]*(obj.ndim+1))
        self._infoOwned = False  ## Do not make changes to _info until it is copied at least once
      
        # We could have checked first whether self._info was already defined:
        #if not hasattr(self, 'info'):
        #    self._info = getattr(obj, 'info', {})
    
  
    def __getitem__(self, ind):
        nInd = self._interpretIndexes(ind)
        #print "Indexes:", nInd
        try:
            a = ndarray.__getitem__(self, nInd)
        except:
            #print nInd, self.shape
            raise
        if type(a) == type(self):  ## generate new info array
            a._info = []
            for i in range(0, len(nInd)):   ## iterate over all axes
                if type(nInd[i]) in [types.SliceType, types.ListType, ndarray] or ndarray in type(nInd[i]).__bases__:  ## If the axis is sliced, keep the info but chop if necessary
                    a._info.append(self._axisSlice(i, nInd[i]))
            a._info.append(self._info[-1])   ## Tack on extra data
        return a
  
    def __getslice__(self, *args):
        return self.__getitem__(slice(*args))
  
    def __setitem__(self, ind, val):
        nInd = self._interpretIndexes(ind)
        try:
            return ndarray.__setitem__(self.view(ndarray), nInd, val)
        except:
            print self, nInd, val
            raise
        
    #def __getattr__(self, attr):
        #if attr in ['round']:
            #return lambda *args, **kwargs: MetaArray(getattr(a.view(ndarray), attr)(*args, **kwargs)
        
  
    def axisValues(self, axis):
        """Return the list of values for an axis"""
        ax = self._interpretAxis(axis)
        if self._info[ax].has_key('values'):
            return self._info[ax]['values']
        else:
            raise Exception('Array axis %s (%d) has no associated values.' % (str(axis), ax))
  
    def xvals(self, axis):
        """Synonym for axisValues()"""
        return self.axisValues(axis)
  
    def axisUnits(self, axis):
        """Return the units for axis"""
        ax = self._info[self._interpretAxis(axis)]
        if ax.has_key('units'):
            return ax['units']
        
    def hasColumn(self, axis, col):
        ax = self._info[self._interpretAxis(axis)]
        if ax.has_key('cols'):
            for c in ax['cols']:
                if c['name'] == col:
                    return True
        return False
        
        
    def columnUnits(self, axis, column):
        """Return the units for column in axis"""
        ax = self._info[self._interpretAxis(axis)]
        if ax.has_key('cols'):
            for c in ax['cols']:
                if c['name'] == column:
                    return c['units']
            raise Exception("Axis %s has no column named %s" % (str(axis), str(column)))
        else:
            raise Exception("Axis %s has no column definitions" % str(axis))
  
    def rowsort(self, axis, key=0):
        """Return this object with all records sorted along axis using key as the index to the values to compare. Does not yet modify meta info."""
        ## make sure _info is copied locally before modifying it!
    
        keyList = self[key]
        order = keyList.argsort()
        if type(axis) == types.IntType:
            ind = [slice(None)]*axis
            ind.append(order)
        elif type(axis) == types.StringType:
            ind = (slice(axis, order),)
        return self[tuple(ind)]
  
    def append(self, val, axis):
        """Return this object with val appended along axis. Does not yet combine meta info."""
        ## make sure _info is copied locally before modifying it!
    
        s = list(self.shape)
        axis = self._interpretAxis(axis)
        s[axis] += 1
        n = MetaArray(tuple(s), info=self._info, dtype=self.dtype)
        ind = [slice(None)]*self.ndim
        ind[axis] = slice(None,-1)
        n[tuple(ind)] = self
        ind[axis] = -1
        n[tuple(ind)] = val
        return n
  
    def extend(self, val, axis):
        """Return the concatenation along axis of this object and val. Does not yet combine meta info."""
        ## make sure _info is copied locally before modifying it!
    
        axis = self._interpretAxis(axis)
        return MetaArray(concatenate(self, val, axis), info=self._info)
  
    def infoCopy(self):
        """Return a deep copy of the axis meta info for this object"""
        return copy.deepcopy(self._info)
  
    def copy(self):
        a = ndarray.copy(self)
        a._info = self.infoCopy()
        return a
  
  
    def _interpretIndexes(self, ind):
        if type(ind) != types.TupleType:
            ind = (ind,)
        nInd = [slice(None)]*self.ndim
        numOk = True  ## Named indices not started yet; numbered sill ok
        for i in range(0,len(ind)):
            (axis, index, isNamed) = self._interpretIndex(ind[i], i, numOk)
            nInd[axis] = index
            if isNamed:
                numOk = False
        return tuple(nInd)
      
    def _interpretAxis(self, axis):
        if type(axis) in [types.StringType, types.TupleType]:
            return self._getAxis(axis)
        else:
            return axis
  
    def _interpretIndex(self, ind, pos, numOk):
        #print "Interpreting index", ind, pos, numOk
        
        
        if MetaArray.isNameType(ind):
            if not numOk:
                raise Exception("string and integer indexes may not follow named indexes")
            #print "  String index, column is ", self._getIndex(pos, ind)
            return (pos, self._getIndex(pos, ind), False)
        elif type(ind) is slice:
            #print "  Slice index"
            if MetaArray.isNameType(ind.start) or MetaArray.isNameType(ind.stop):  ## Not an actual slice!
                #print "    ..not a real slice"
                axis = self._interpretAxis(ind.start)
                #print "    axis is", axis
                
                ## x[Axis:Column]
                if MetaArray.isNameType(ind.stop):
                    #print "    column name, column is ", self._getIndex(axis, ind.stop)
                    index = self._getIndex(axis, ind.stop)
                    
                ## x[Axis:min:max]
                elif (type(ind.stop) is float or type(ind.step) is float) and ('values' in self._info[axis]):
                    #print "    axis value range"
                    if ind.stop is None:
                        mask = self.xvals(axis) < ind.step
                    elif ind.step is None:
                        mask = self.xvals(axis) > ind.stop
                    else:
                        mask = (self.xvals(axis) > ind.stop) * (self.xvals(axis) < ind.step)
                    index = mask
                    
                ## x[Axis:columnIndex]
                elif type(ind.stop) is int or type(ind.step) is int:
                    #print "    normal slice after named axis"
                    if ind.step is None:
                        index = ind.stop
                    else:
                        index = slice(ind.stop, ind.step)
                    
                ## x[Axis: [list]]
                elif type(ind.stop) is list:
                    index = []
                    for i in ind.stop:
                        if type(i) is int:
                            index.append(i)
                        elif MetaArray.isNameType(i):
                            index.append(self._getIndex(axis, i))
                        else:
                            ## unrecognized type, try just passing on to array
                            index = ind.stop
                            break
                
                else:
                    #print "    other type.. forward on to array for handling"
                    index = ind.stop
                #print "Axis %s (%s) : %s" % (ind.start, str(axis), str(type(index)))
                #if type(index) is ndarray:
                    #print "    ", index.shape
                return (axis, index, True)
            else:
                #print "  Looks like a real slice, passing on to array"
                return (pos, ind, False)
        elif type(ind) is list:
            #print "  List index., interpreting each element individually"
            indList = [self._interpretIndex(i, pos, numOk)[1] for i in ind]
            return (pos, indList, False)
        else:
            if not numOk:
                raise Exception("string and integer indexes may not follow named indexes")
            #print "  normal numerical index"
            return (pos, ind, False)
  
    def _getAxis(self, name):
        for i in range(0, len(self._info)):
            axis = self._info[i]
            if axis.has_key('name') and axis['name'] == name:
                return i
        raise Exception("No axis named %s.\n  info=%s" % (name, self._info))
  
    def _getIndex(self, axis, name):
        ax = self._info[axis]
        if ax is not None and ax.has_key('cols'):
            for i in range(0, len(ax['cols'])):
                if ax['cols'][i].has_key('name') and ax['cols'][i]['name'] == name:
                    return i
        raise Exception("Axis %d has no column named %s.\n  info=%s" % (axis, name, self._info))
  
    def _axisCopy(self, i):
        return copy.deepcopy(self._info[i])
  
    def _axisSlice(self, i, cols):
        if self._info[i].has_key('cols') or self._info[i].has_key('values'):
            ax = self._axisCopy(i)
            if ax.has_key('cols'):
                ax['cols'] = list(array(ax['cols'])[cols])
            if ax.has_key('values'):
                ax['values'] = array(ax['values'])[cols]
        else:
            ax = self._info[i]
        return ax
  
    def __repr__(self):
        return "%s\n  axis info: %s" % (ndarray.__repr__(self), str(self._info))

    def __str__(self):
        return self.__repr__()


    #### File I/O Routines

    @staticmethod
    def _readMeta(fd):
        """Read meta array from the top of a file. Read lines until a blank line is reached.
        This function should ideally work for ALL versions of MetaArray.
        """
        meta = ''
        ## Read meta information until the first blank line
        while True:
            line = fd.readline().strip()
            if line == '':
                break
            meta += line
        return eval(meta)

    @staticmethod
    def _readData1(fd, meta, subtype):
        """Read array data from the file descriptor for MetaArray v1 files
        """
        ## read in axis values for any axis that specifies a length
        frameSize = 1
        for ax in meta['info']:
            if ax.has_key('values_len'):
                ax['values'] = fromstring(fd.read(ax['values_len']), dtype=ax['values_type'])
                frameSize *= ax['values_len']
                del ax['values_len']
                del ax['values_type']
        ## the remaining data is the actual array
        subarr = fromstring(fd.read(), dtype=meta['type'])
        subarr = subarr.view(subtype)
        subarr.shape = meta['shape']
        subarr._info = meta['info']
        return subarr
            
    @staticmethod
    def _readData2(fd, meta, subtype):
        ## read in axis values
        dynAxis = None
        frameSize = 1
        ## read in axis values for any axis that specifies a length
        for i in range(len(meta['info'])):
            ax = meta['info'][i]
            if ax.has_key('values_len'):
                if ax['values_len'] == 'dynamic':
                    if dynAxis is not None:
                        raise Exception("MetaArray has more than one dynamic axis! (this is not allowed)")
                    dynAxis = i
                else:
                    ax['values'] = fromstring(fd.read(ax['values_len']), dtype=ax['values_type'])
                    frameSize *= ax['values_len']
                    del ax['values_len']
                    del ax['values_type']
                    
        ## No axes are dynamic, just read the entire array in at once
        if dynAxis is None:
            if meta['type'] == 'object':
                subarr = pickle.loads(fd.read())
            else:
                subarr = fromstring(fd.read(), dtype=meta['type'])
            #subarr = subarr.view(subtype)
            subarr.shape = meta['shape']
            #subarr._info = meta['info']
        ## One axis is dynamic, read in a frame at a time
        else:
            ax = meta['info'][dynAxis]
            xVals = []
            frames = []
            frameShape = list(meta['shape'])
            frameShape[dynAxis] = 1
            frameSize = reduce(lambda a,b: a*b, frameShape)
            n = 0
            while True:
                ## Extract one non-blank line
                while True:
                    line = fd.readline()
                    if line != '\n':
                        break
                if line == '':
                    break
                    
                ## evaluate line
                inf = eval(line)
                
                ## read data block
                #print "read %d bytes as %s" % (inf['len'], meta['type'])
                if meta['type'] == 'object':
                    data = pickle.loads(fd.read(inf['len']))
                else:
                    data = fromstring(fd.read(inf['len']), dtype=meta['type'])
                
                if data.size != frameSize * inf['numFrames']:
                    #print data.size, frameSize, inf['numFrames']
                    raise Exception("Wrong frame size in MetaArray file! (frame %d)" % n)
                    
                ## read in data block
                shape = list(frameShape)
                shape[dynAxis] = inf['numFrames']
                data.shape = shape
                frames.append(data)
                
                n += inf['numFrames']
                if 'xVals' in inf:
                    xVals.extend(inf['xVals'])
            subarr = concatenate(frames, axis=dynAxis)
            if len(xVals)> 0:
                ax['values'] = array(xVals, dtype=ax['values_type'])
            del ax['values_len']
            del ax['values_type']
        subarr = subarr.view(subtype)
        subarr._info = meta['info']
        return subarr
                    
    def write(self, fileName, appendAxis=None, newFile=False):
        """Write this object to a file. The object can be restored by calling MetaArray(file=fileName)"""
    
        meta = {'shape':self.shape, 'type':str(self.dtype), 'info':self.infoCopy(), 'version':MetaArray.version}
        axstrs = []
        
        ## copy out axis values for dynamic axis if requested
        if appendAxis is not None:
            if MetaArray.isNameType(appendAxis):
                appendAxis = self._interpretAxis(appendAxis)
            
            
            ax = meta['info'][appendAxis]
            ax['values_len'] = 'dynamic'
            if 'values' in ax:
                ax['values_type'] = str(ax['values'].dtype)
                dynXVals = ax['values']
                del ax['values']
            else:
                dynXVals = None
                
        ## Generate axis data string, modify axis info so we know how to read it back in later
        for ax in meta['info']:
            if 'values' in ax:
                axstrs.append(ax['values'].tostring())
                ax['values_len'] = len(axstrs[-1])
                ax['values_type'] = str(ax['values'].dtype)
                del ax['values']
                
        ## Decide whether to output the meta block for a new file
        if not newFile:
            ## If the file does not exist or its size is 0, then we must write the header
            newFile = (not os.path.exists(fileName))  or  (os.stat(fileName).st_size == 0)
        
        ## write data to file
        if appendAxis is None or newFile:
            fd = open(fileName, 'wb')
            fd.write(str(meta) + '\n\n')
            for ax in axstrs:
                fd.write(ax)
        else:
            fd = open(fileName, 'ab')
        
        if self.dtype != object:
            dataStr = self.view(ndarray).tostring()
        else:
            dataStr = pickle.dumps(self.view(ndarray))
        #print self.size, len(dataStr), self.dtype
        if appendAxis is not None:
            frameInfo = {'len':len(dataStr), 'numFrames':self.shape[appendAxis]}
            if dynXVals is not None:
                frameInfo['xVals'] = list(dynXVals)
            fd.write('\n'+str(frameInfo)+'\n')
        fd.write(dataStr)
        fd.close()
  
    def writeCsv(self, fileName=None):
        """Write 2D array to CSV file or return the string if no filename is given"""
        if self.ndim > 2:
            raise Exception("CSV Export is only for 2D arrays")
        if fileName is not None:
            file = open(fileName, 'w')
        ret = ''
        if self._info[0].has_key('cols'):
            s = ','.join([x['name'] for x in self._info[0]['cols']]) + '\n'
            if fileName is not None:
                file.write(s)
            else:
                ret += s
        for row in range(0, self.shape[1]):
            s = ','.join(["%g" % x for x in self[:, row]]) + '\n'
            if fileName is not None:
                file.write(s)
            else:
                ret += s
        if fileName is not None:
            file.close()
        else:
            return ret
        




  
  