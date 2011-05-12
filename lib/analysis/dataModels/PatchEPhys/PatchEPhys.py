# -*- coding: utf-8 -*-
import DataManager
import SequenceRunner
from advancedTypes import OrderedDict
import functools
from metaarray import *

protocolNames = {
    'IV Curve': ('cciv.*', 'vciv.*'),
    'Photostim Scan': (),
    'Photostim Power Series': (),
}
    
     
deviceNames = {
    'Clamp': ('Clamp1', 'Clamp2', 'AxoPatch200', 'AxoProbe'),
    'Camera': ('Camera'),
    'Laser': ('Laser-UV', 'Laser-Blue')
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
    
def dirType(dh):
    """Return a string representing the type of data stored in a directory.
    Usually, this is provided in the meta-info for the directory, but in a few
    cases we need to do a little more probing."""
    info = dh.info()
    type = info.get('dirType', None)
    if type is None:
        if '__object_type__' in info:
            type = info['__object_type__']
        elif 'protocol' in info:
            if 'sequenceParams' in info:
                type = 'ProtocolSequence'  
            else:
                type = 'Protocol'  ## an individual protocol run, NOT a single run from within a sequence
        
        else:
            try:
                if dirType(dh.parent()) == 'ProtocolSequence':
                    type = 'Protocol'
                else:
                    raise Exception()
            except:
                raise Exception("Can't determine type for dir %s" % dh.name())
    return type

def listSequenceParams(dh):
    """Given a directory handle for a protocol sequence, return the dict of sequence parameters"""
    try:
        return dh.info()['sequenceParams']
    except KeyError:
        raise Exception("Directory '%s' does not appear to be a protocol sequence." % dh.name())

def buildSequenceArray(dh, func):
    """Builds a MetaArray of data compiled across a sequence. 
    Arguments:
        dh:   directory handle for the protocol sequence
        func: a function that returns an array or scalar, given a protocol dir handle.
        
    Example: Return an array of all primary-channel clamp recordings across a sequence 
        buildSequenceArray(seqDir, lambda protoDir: getClampFile(protoDir).read()['primary'])"""
    params = listSequenceParams(dh)
    inds = OrderedDict([(k, range(len(v))) for k,v in params.iteritems()])
    def runFunc(dh, func, params):
        name = '_'.join(['%03d'%n for n in params.values()])
        fh = dh[name]
        return func(fh)
    data = SequenceRunner.runSequence(functools.partial(runFunc, dh, func), inds, inds.keys())
    
    ## Pick up more meta info if available
    subd = dh.subDirs()
    if len(subd) > 0:
        d1 = func(dh[subd[0]])
        data._info = data._info[:len(params)] + d1._info
        
    ## correct parameter values
    for i in range(len(params)):
        vals = params.values()[i]
        data._info[i]['values'] = vals
        
    return data


def getClampFile(protoDH):
    """Given a protocol directory handle, return the clamp file handle within. 
    If there are multiple clamps, only the first is returned.
    Return None if no clamps are found."""
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
    
def isCell(dh):
    if dh.name()[-8:-4] == 'cell':
        return True
    else:
        return False
    
    
    
def getClampCommand(data, generateEmpty=True):
    """Returns the command data from a clamp MetaArray.
    If there was no command specified, the function will optionally return all zeros."""
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
            return MetaArray(zeros(tVals.shape), info=[{'name': 'Time', 'values': tVals, 'units': 's'}, {'units': units}])
    return None

def getClampPrimary(data):
    """Return primary channel from """
    if data.hasColumn('Channel', 'primary'):
        return data['Channel': 'primary']
    else:
        return data['Channel': 'scaled']
    
    
def getClampMode(data):
    """Given a clamp file handle or MetaArray, return the recording mode."""
    if not isinstance(data, MetaArray):
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
    sinfo = fh.parentDir.info()
    
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
        
def getDayInfo(dh):
    while dirType(dh) != 'Day':
        dh = dh.parent()
    return dh.info()

def getCellInfo(dh):
    while dirType(dh) not in ['Cell']:
        dh = dh.parent()
    return dh.info()

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
    return cellInfo.get('type', '')

    

