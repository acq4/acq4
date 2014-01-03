# -*- coding: utf-8 -*-
import acq4.util.DataManager as DataManager
import acq4.util.SequenceRunner as SequenceRunner
from collections import OrderedDict
import functools
from acq4.util.metaarray import *
import numpy as np

protocolNames = {
    'IV Curve': ('cciv.*', 'vciv.*'),
    'Photostim Scan': (),
    'Photostim Power Series': (),
}
    
     
deviceNames = {
    'Clamp': ('Clamp1', 'Clamp2', 'AxoPatch200', 'AxoProbe'),
    'Camera': ('Camera'),
    'Laser': ('Laser-UV', 'Laser-Blue', 'Laser-2P')
}


"""Function library for formalizing the raw data structures used in analysis.
This provides a layer of abstraction between the raw data and the analysis routines.

Should allow simple questions like
    Were any scan protocols run under this cell?
    Is this a sequence protocol or a single?
    Give me a meta-array linking all of the data in a sequence (will have to use hdf5 for this?)
    Give me a meta-array of all images from 'Camera' in a sequence (will have to use hdf5 for this?)
    
    Give me the clamp device for this protocol run
    tell me the temperature of this run
    tell me the holding potential for this clamp data
    possibly DB integration?
    
    When did the laser stimulation occur, for how long, and at what power level?
    
Notes:
    Should be able to easily switch to a different data model
    
"""

def isSequence(dh):
    """Return true if dh is a directory handle for a protocol sequence."""
    return dirType(dh) == 'ProtocolSequence'
    #if 'sequenceParams' in dh.info():
        #return True
    #else:
        #return False
    
def dirType(dh, allowRecurse=True):
    """
    Return a string representing the type of data stored in a directory.
    Usually, this is provided in the meta-info for the directory, but in a few
    cases (old data formats) we need to do a little more probing.
    Returns None if the type cannot be determined.
    """
    info = dh.info()
    type = info.get('dirType', None)
    if type is None:
        if '__object_type__' in info:
            type = info['__object_type__']
        elif dh.name()[-5:] == 'Patch':
            type = 'Patch'
        elif 'protocol' in info:
            if 'sequenceParams' in info:
                type = 'ProtocolSequence'  
            else:
                type = 'Protocol'  ## an individual protocol run, NOT a single run from within a sequence
        
        else:
            try:
                assert allowRecurse
                parent = dh.parent()
                if dirType(parent, allowRecurse=False) == 'ProtocolSequence':
                    type = 'Protocol'
                #else:
                    #raise Exception()
            except:
                pass
                #raise Exception("Can't determine type for dir %s" % dh.name())
    return type

def listSequenceParams(dh):
    """Given a directory handle for a protocol sequence, return the dict of sequence parameters"""
    try:
        return dh.info()['sequenceParams']
    except KeyError:
        raise Exception("Directory '%s' does not appear to be a protocol sequence." % dh.name())

## what's this for?
#def listWaveGenerator(dh):
#    try:
#        return dh.info()['waveGeneratorWidget']
#    except KeyError:
#        raise Exception("Directory '%s' does not appear to be have a wave Generator." % dh.name())

def buildSequenceArray(*args, **kargs):
    """Builds a MetaArray of data compiled across a sequence. 
    Arguments:
        dh:      directory handle for the protocol sequence
        func:    a function (optional) that returns an array or scalar, given a protocol dir handle.
                 If func is None, return an object array containing the DirHandles (forces join=False)
        join:    If True (default), attempt to join all results into a single array. This assumes that
                 func returns arrays of equal shape for every point in the parameter space.
                 If False, just return an object array pointing to individual results.
        truncate: If join=True and some elements differ in shape, truncate to the smallest shape
        fill:    If join=True, pre-fill the empty array with this value. Any points in the
                 parameter space with no data will be left with this value.
        
    Example: Return an array of all primary-channel clamp recordings across a sequence 
        buildSequenceArray(seqDir, lambda protoDir: getClampFile(protoDir).read()['primary'])"""
        
    for i,m in buildSequenceArrayIter(*args, **kargs):
        if m is None:
            return i
        
def buildSequenceArrayIter(dh, func=None, join=True, truncate=False, fill=None):
    """Iterator for buildSequenceArray that yields progress updates."""
        
    if func is None:
        func = lambda dh: dh
        join = False
        
    params = listSequenceParams(dh)
    #inds = OrderedDict([(k, range(len(v))) for k,v in params.iteritems()])
    #def runFunc(dh, func, params):
        #name = '_'.join(['%03d'%n for n in params.values()])
        #fh = dh[name]
        #return func(fh)
    #data = SequenceRunner.runSequence(functools.partial(runFunc, dh, func), inds, inds.keys())
    subDirs = dh.subDirs()
    if len(subDirs) == 0:
        yield None, None
    
    ## set up meta-info for sequence axes
    seqShape = tuple([len(p) for p in params.itervalues()])
    info = [[] for i in range(len(seqShape))]
    i = 0
    for k,v in params.iteritems():
        info[i] = {'name': k, 'values': np.array(v)}
        i += 1
    
    ## get a data sample
    first = func(dh[subDirs[0]])
    
    ## build empty MetaArray
    if join:
        shape = seqShape + first.shape
        if isinstance(first, MetaArray):
            info = info + first._info
        else:
            info = info + [[] for i in range(first.ndim+1)]
        data = MetaArray(np.empty(shape, first.dtype), info=info)
        if fill is not None:
            data[:] = fill
        
    else:
        shape = seqShape
        info = info + []
        data = MetaArray(np.empty(shape, object), info=info)
    
    
    ## fill data
    i = 0
    if join and truncate:
        minShape = first.shape
        for name in subDirs:
            subd = dh[name]
            d = func(subd)
            minShape = [min(d.shape[j], minShape[j]) for j in range(d.ndim)]
            dhInfo = subd.info()
            ind = []
            for k in params:
                ind.append(dhInfo[k])
            sl = [slice(0,m) for m in minShape]
            ind += sl
            data[tuple(ind)] = d[sl]
            i += 1
            yield i, len(subDirs)
        sl = [slice(None)] * len(seqShape)
        sl += [slice(0,m) for m in minShape]
        data = data[sl]
    else:
        for name in subDirs:
            subd = dh[name]
            d = func(subd)
            dhInfo = subd.info()
            ind = []
            for k in params:
                ind.append(dhInfo[k])
            data[tuple(ind)] = d
            i += 1
            yield i, len(subDirs)
        
    
    yield data, None

def getParent(child, parentType):
    """Return the (grand)parent of child that matches parentType"""
    if dirType(child) == parentType:
        return child
    parent = child.parent()
    if parent is child:
        return None
    return getParent(parent, parentType)
    


def getClampFile(protoDH):
    """Given a protocol directory handle, return the clamp file handle within. 
    If there are multiple clamps, only the first is returned.
    Return None if no clamps are found."""
    if protoDH.name()[-8:] == 'DS_Store': ## OS X filesystem puts .DS_Store files in all directories
        return None
    files = protoDH.ls()
    names = deviceNames['Clamp']
    for n in names:
        if n in files: 
            return protoDH[n]
        if n+'.ma' in files:
            return protoDH[n+'.ma']
    return None

def isClampFile(fh):
    if fh.shortName() not in deviceNames['Clamp'] and fh.shortName()[:-3] not in deviceNames['Clamp']:
        return False
    else:
        return True
        
def getClampCommand(data, generateEmpty=True):    
    """Returns the command data from a clamp MetaArray.
    If there was no command specified, the function will return all zeros if generateEmpty=True (default)."""
    
    if data.hasColumn('Channel', 'Command'):
        return data['Channel': 'Command']
    elif data.hasColumn('Channel', 'command'):
        return data['Channel': 'command']
    else:
        if generateEmpty:
            tVals = data.xvals('Time')
            mode = getClampMode(data)
            if 'v' in mode.lower():
                units = 'V'
            else:
                units = 'A'
            return MetaArray(np.zeros(tVals.shape), info=[{'name': 'Time', 'values': tVals, 'units': 's'}, {'units': units}])
    return None

def getClampPrimary(data):
    """Return primary channel from """
    if data.hasColumn('Channel', 'primary'):
        return data['Channel': 'primary']
    else:
        return data['Channel': 'scaled']
    
    
def getClampMode(data):
    """Given a clamp file handle or MetaArray, return the recording mode."""
    if not (hasattr(data, 'implements') and data.implements('MetaArray')):
        if not isClampFile(data):
            raise Exception('%s not a clamp file.' %fh.shortName())
        data = data.read()
    info = data._info[-1]
    
    if 'ClampState' in info:
        return info['ClampState']['mode']
    else:
        try:
            mode = info['mode']
            return mode
        except KeyError:
            return None

def getClampHoldingLevel(fh):
    """Given a clamp file handle, return the holding level (voltage for VC, current for IC).
    TODO: This function should add in the amplifier's internal holding value, if available?
    """
    
    if not isClampFile(fh):
        raise Exception('%s not a clamp file.' %fh.shortName())
    
    data = fh.read()
    info = data._info[-1]
    p1 = fh.parent()
    p2 = p1.parent()
    if isSequence(p2):
        sinfo = p2.info()
    else:
        sinfo = p1.info()
    
    ## There are a few places we could find the holding value, depending on how old the data is
    if 'ClampState' in info and 'holding' in info['ClampState']:
        return info['ClampState']['holding']
    elif 'DAQ' in info and 'command' in info['DAQ'] and 'holding' in info['DAQ']['command']:
        return info['DAQ']['command']['holding']
    else:
        try:
            if fh.shortName()[-3:] == '.ma':
                name = fh.shortName()[:-3]
            else:
                name = fh.shortName()
            holding = float(sinfo['devices'][name]['holdingSpin']) ## in volts
            return holding
        except KeyError:
            return None
        

def getSampleRate(data):
    """given clamp data, return the data sampling rate """
    #data = fh.read()
    info = data._info[-1]
    if 'DAQ' in info.keys():
        return(info['DAQ']['primary']['rate'])
    else:
        return(info['rate'])
    
def getParentInfo(dh, parentType):
    dh = getParent(dh, parentType)
    if dh is None:
        return None
    else:
        return dh.info()
    
def getDayInfo(dh):
    return getParentInfo(dh, 'Day')
    
def getSliceInfo(dh):
    return getParentInfo(dh, 'Slice')

def getCellInfo(dh):
    return getParentInfo(dh, 'Cell')

def getACSF(dh):
    dayInfo = getDayInfo(dh)
    return dayInfo.get('solution', '')
    
def getInternalSoln(dh):
    dayInfo = getDayInfo(dh)
    return dayInfo.get('internal', '')

def getTemp(dh):
    if dh.isFile():
        dh = dh.parent()
    temp = dh.info().get(('Temperature','BathTemp'), None)
    if temp == None:
        temp = getDayInfo(dh).get('temperature', '')
    return temp

def getCellType(dh):
    cellInfo = getCellInfo(dh)
    if cellInfo is not None:
        return cellInfo.get('type', '')
    else:
        return('Unknown')
    

