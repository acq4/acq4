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

# note: make sure the names, if single, are followed by ',', so as to enforce elements of tuple
deviceNames = {
    'Clamp': ('Clamp1', 'Clamp2', 'AxoPatch200', 'AxoProbe', 'MultiClamp1', 'MultiClamp2'),
    'Camera': ('Camera',),
    'Laser': ('Laser-UV', 'Laser-Blue', 'Laser-2P'),
    'LED-Blue': ('LED-Blue',),
}

# current and voltage clamp modes that are know to us
ic_modes = ['IC', 'CC', 'IClamp', 'ic', 'I-Clamp Fast', 'I-Clamp Slow']
vc_modes = ['VC', 'VClamp', 'vc']  # list of VC modes


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

def knownClampNames():
    return deviceNames['Clamp']

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
            info = info + [{} for i in range(first.ndim+1)]
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
    """
    Given a protocol directory handle, return the clamp file handle within.
    If there are multiple clamps, only the first one encountered in deviceNames is returned.
    Return None if no clamps are found.
    """
    if protoDH.name()[-8:] == 'DS_Store': ## OS X filesystem puts .DS_Store files in all directories
        return None
    files = protoDH.ls()
    for n in deviceNames['Clamp']:
        if n in files:
            return protoDH[n]
        if n+'.ma' in files:
            return protoDH[n+'.ma']
    #print 'getClampFile: did not find protocol for clamp: ', files
    #print 'valid devices: ', deviceNames['Clamp']
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

def getClampMode(data_handle, dir_handle=None):
    """Given a clamp file handle or MetaArray, return the recording mode."""
    if (hasattr(data_handle, 'implements') and data_handle.implements('MetaArray')):
        data = data_handle
    elif isClampFile(data_handle):
        data = data_handle.read(readAllData=False)
    else:
        raise Exception('%s not a clamp file.' % data)
    # if isClampFile(data_handle):
    #     data = data_handle.read(readAllData=False)
    # else:
    #     data = data_handle
    info = data._info[-1]
    if 'ClampState' in info:
        return info['ClampState']['mode']
    else:

        try:
            mode = info['mode'] # if the mode is in the info (sometimes), return that
            return mode
        except KeyError:
            raise KeyError('PatchEPhys, getClampMode: Cannot determine clamp mode for this data')
            # if dir_handle is not None:
            #     devs =  dir_handle.info()['devices'].keys()  # get devices in parent directory
            #     for dev in devs:  # for all the devices
            #         if dev in deviceNames['Clamp']:  # are any clamps?
            #            # print 'device / keys: ', dev, dir_handle.info()['devices'][dev].keys()
            #             #print  'mode: ', dir_handle.info()['devices'][dev]['mode']
            #             return dir_handle.info()['devices'][dev]['mode']
            # else:
            #     return 'vc'  # None  kludge to handle simulations, which don't seem to fully fill the structures.

def getClampHoldingLevel(data_handle):
    """Given a clamp file handle, return the holding level (voltage for VC, current for IC).
    TODO: This function should add in the amplifier's internal holding value, if available?
    """
    if not isClampFile(data_handle):
        raise Exception('%s not a clamp file.' % data_handle.shortName())
    
    data = data_handle.read(readAllData=False)
    info = data._info[-1]
    p1 = data_handle.parent()
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
            if data_handle.shortName()[-3:] == '.ma':
                name = data_handle.shortName()[:-3]
            else:
                name = data_handle.shortName()
            holding = float(sinfo['devices'][name]['holdingSpin']) ## in volts
            return holding
        except KeyError:
            return None

def getClampState(data_handle):
    """
    Return the full clamp state
    """
    if not isClampFile(data_handle):
        raise Exception('%s not a clamp file.' % data_handle.shortName())
    data = data_handle.read(readAllData=False)
    info = data._info[-1]
    if 'ClampState' in info.keys():
        return info['ClampState']
    else:
        return None

def getWCCompSettings(data_handle):
    """
    return the compensation settings, if available
    Settings are returned as a group in a dictionary
    """
    if not isClampFile(data_handle):
        raise Exception('%s not a clamp file.' % data_handle.shortName())
    data = data_handle.read(readAllData=False)
    info = data._info[-1]
    d = {}
    if 'ClampState' in info.keys() and 'ClampParams' in info['ClampState'].keys():
        par = info['ClampState']['ClampParams']
        d['WCCompValid'] = True
        d['WCEnabled'] = par['WholeCellCompEnable']
        d['WCResistance'] = par['WholeCellCompResist']
        d['WCCellCap'] = par['WholeCellCompCap']
        d['CompEnabled'] = par['RsCompEnable']
        d['CompCorrection'] = par['RsCompCorrection']
        d['CompBW'] = par['RsCompBandwidth']
        return d
    else:
        return {'WCCompValid': False, 'WCEnable': 0, 'WCResistance': 0., 'WholeCellCap': 0.,
                'CompEnable': 0, 'CompCorrection': 0., 'CompBW': 50000. }

def getBridgeBalanceCompensation(data_handle):
    """Return the bridge balance compensation setting for current clamp data, if bridge balance compensation was enabled.

            data_handle    A MetaArray file or clamp file handle."""

    if (hasattr(data_handle, 'implements') and data_handle.implements('MetaArray')):
        data = data_handle
    elif isClampFile(data_handle):
        data = data_handle.read(readAllData=False)
    else:
        raise Exception('%s not a clamp file.' % data)


    mode = getClampMode(data)
    global ic_modes
    if mode not in ic_modes:
        raise Exception("Data is in %s mode, not a current clamp mode, and therefore bridge balance compensation is not applicable." %str(mode))

    info = data.infoCopy()[-1]
    bridgeEnabled = info.get('ClampState', {}).get('ClampParams', {}).get('BridgeBalEnable', None)
    if bridgeEnabled is None:
        raise Exception('Could not find whether BridgeBalance compensation was enabled for the given data.')
    elif not bridgeEnabled:
        return 0.0
    else:
        bridge = info.get('ClampState', {}).get('ClampParams', {}).get('BridgeBalResist', None)
        if bridge is not None:
            return bridge
        else:
            raise Exception('Could not find BridgeBalanceCompensation value for the given data.')


def getSampleRate(data_handle):
    """given clamp data, return the data sampling rate """
    if not isClampFile(data_handle):
        raise Exception('%s not a clamp file.' % data_handle.shortName())
    data = data_handle.read(readAllData=False)
    info = data._info[-1]
    if 'DAQ' in info.keys():
        return(info['DAQ']['primary']['rate'])
    else:
        return(info['rate'])

def getDevices(protoDH):
    """
    return a dictionary of all the (recognized) devices and their file handles in the protocol directory
    This can be handy to check which devices were recorded during a protocol (the keys of the dictionary)
    and for accessing the data (from the file handles)
    pbm 5/2014
    """
    if protoDH.name()[-8:] == 'DS_Store': ## OS X filesystem puts .DS_Store files in all directories
        return None
    files = protoDH.ls()
    devList = {}
    for devname in deviceNames.keys():
        names = deviceNames[devname]
        for n in names:
            if n in files:
                devList[n] = protoDH[n]
            elif n+'.ma' in files:
                devList[n] = protoDH[n+'.ma']
            else:
                pass
    if len(devList) == 0:
        return None
    return devList


def getClampDeviceNames(protoDH):
    """
    get the Clamp devices used in the current protocol
    :param protoDH: handle to current protocol
    :return clampDeviceNames: The names of the clamp devices used in this protocol, or None if no devices 
    """
    if protoDH.name()[-8:] == 'DS_Store': ## OS X filesystem puts .DS_Store files in all directories
        return None
    files = protoDH.ls()
    clampDeviceNames = []
    for knownDevName in deviceNames['Clamp']:  # go through known devices
        if knownDevName in files:
            clampDeviceNames.append(knownDevName)
        elif knownDevName+'.ma' in files:
            clampDeviceNames.append(knownDevName)
        else:
                pass
    if len(clampDeviceNames) == 0:
        return None
    return clampDeviceNames


def getNamedDeviceFile(protoDH, deviceName):
    """Given a protocol directory handle, return the requested device file handle within.
    If there are multiple devices, only the first is returned.
    Return None if no matching devices are found.
    """
    if protoDH.name()[-8:] == 'DS_Store': ## OS X filesystem puts .DS_Store files in all directories
        return None
    if deviceName in deviceNames.keys():
        names = deviceNames[deviceName]
    else:
        return None
    files = protoDH.ls()
    for n in names:
        if n in files:
            return protoDH[n]
        if n+'.ma' in files:
            return protoDH[n+'.ma']
    return None

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
    if dayInfo is not None:
        return dayInfo.get('solution', '')
    return None
    
def getInternalSoln(dh):
    dayInfo = getDayInfo(dh)
    if dayInfo is not None:
        return dayInfo.get('internal', '')
    return None

def getTemp(dh):
    if dh.isFile():
        dh = dh.parent()
    temp = dh.info().get(('Temperature','BathTemp'), None)
    if temp is None:
        dayinfo = getDayInfo(dh)
        if dayinfo is not None:
            temp = getDayInfo(dh).get('temperature', '')
    return temp

def getCellType(dh):
    cellInfo = getCellInfo(dh)
    if cellInfo is not None:
        return cellInfo.get('type', '')
    else:
        return('Unknown')
        
def file_cell_protocol(filename):
    """
    file_cell_protocol breaks the current filename down and returns a
    tuple: (date, sliceid, cell, proto, parent directory)
    last argument returned is the rest of the path...
    """
    (p0, proto) = os.path.split(filename)
    (p1, cell) = os.path.split(p0)
    (p2, sliceid) = os.path.split(p1)
    (parentdir, date) = os.path.split(p2)
    return date, sliceid, cell, proto, parentdir

def cell_summary(dh, summary=None):
    """
    cell_summary generates a dictionary of information about the cell
    for the selected directory handle (usually a protocol; could be a file)
    :param dh: the directory handle for the data, as passed to loadFileRequested
    :return summary dictionary:
    """
    # other info into a dictionary
    if summary is None:
        summary = {}
    summary['Day'] = getDayInfo(dh)
    summary['Slice'] = getSliceInfo(dh)
    summary['Cell'] = getCellInfo(dh)
    summary['ACSF'] = getACSF(dh)
    summary['Internal'] = getInternalSoln(dh)
    summary['Temperature'] = getTemp(dh)
    summary['CellType'] = getCellType(dh)
    today = summary['Day']

    if today is not None:
        if 'species' in today.keys():
            summary['Species'] = today['species']
        if 'age' in today.keys():
            summary['Age'] = today['age']
        if 'sex' in today.keys():
            summary['Sex'] = today['sex']
        if 'weight' in today.keys():
            summary['Weight'] = today['weight']
        if 'temperature' in today.keys():
            summary['Temperature'] = today['temperature']
        if 'description' in today.keys():
            summary['Description'] = today['description']
    else:
        for k in ['species', 'age', 'sex', 'weight', 'temperature', 'description']:
            summary[k] = None
    if summary['Cell'] is not None:
        ct = summary['Cell']['__timestamp__']
    else:
        ct = 0.
    pt = dh.info()['__timestamp__']
    summary['ElapsedTime'] = pt - ct  # save elapsed time between cell opening and protocol start
    (date, sliceid, cell, proto, parentdir) = file_cell_protocol(dh.name())
    summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the ID for the cell later on
    summary['Protocol'] = proto
    return summary


# noinspection PyPep8
class GetClamps():
    """
    Convience class to read voltage and current clamp data from files, including collating data from
    a protocol. The results are stored in class variables. Handles variations in file structure
    from early versions of Acq4 including returning the stimulus waveforms.
    This class will usually be called from the LoadFileRequested routine in an analysis module.
    """
    def __init__(self):
        pass

    def getClampData(self, dh, pars=None):
        """
        Read the clamp data - whether it is voltage or current clamp, and put the results
        into our class variables. 
        dh is the file handle (directory)
        pars is a structure that provides some control parameters usually set by the GUI
        Returns a short dictionary of some values; others are accessed through the class.
        Returns None if no data is found.
        """   
        pars = self.getParsDefaults(pars)
        clampInfo = {}
        if dh is None:
            return None

        dirs = dh.subDirs()
        clampInfo['dirs'] = dirs
        traces = []
        cmd = []
        cmd_wave = []
        data = []
        self.time_base = None
        self.values = []
        self.trace_StartTimes = np.zeros(0)
        sequence_values = None
        self.sequence = listSequenceParams(dh)
        # building command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')

        if clamp in self.sequence:
            self.clampValues = self.sequence[clamp]
            self.nclamp = len(self.clampValues)
            if sequence_values is not None:
                # noinspection PyUnusedLocal
                sequence_values = [x for x in self.clampValues for y in sequence_values]
            else:
                sequence_values = [x for x in self.clampValues]
        else:
            sequence_values = []
#            nclamp = 0

        # if sequence has repeats, build pattern
        if reps in self.sequence:
            self.repc = self.sequence[reps]
            self.nrepc = len(self.repc)
            # noinspection PyUnusedLocal
            sequence_values = [x for y in range(self.nrepc) for x in sequence_values]

        # select subset of data by overriding the directory sequence...
            dirs = []
###
### This is possibly broken -
### 
###
            ld = pars['sequence1']['index']
            rd = pars['sequence2']['index']
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(pars['sequence2']['count'])
                if rd[0] == -1:  # 'All'
                    rd = range(pars['sequence2']['count'])

                for i in ld:
                    for j in rd:
                        dirs.append('%03d_%03d' % (i, j))
### --- end of possibly broken section

        for i, directory_name in enumerate(dirs):  # dirs has the names of the runs withing the protocol
            data_dir_handle = dh[directory_name]  # get the directory within the protocol
            try:
                data_file_handle = getClampFile(data_dir_handle)  # get pointer to clamp data
                # Check if there is no clamp file for this iteration of the protocol
                # Usually this indicates that the protocol was stopped early.
                if data_file_handle is None:
                    print 'PatchEPhys/GetClamps: Missing data in %s, element: %d' % (directory_name, i)
                    continue
            except:
                raise Exception("Error loading data for protocol %s:"
                                % directory_name)
            data_file = data_file_handle.read()

            self.data_mode  = getClampMode(data_file, dir_handle=dh)
            if self.data_mode is None:
                self.data_mode = ic_modes[0]  # set a default mode
            if self.data_mode in ['vc']:  # should be "AND something"  - this is temp fix for Xuying's old data
                self.data_mode = vc_modes[0]
            if self.data_mode in ['model_ic', 'model_vc']:  # lower case means model was run
                self.modelmode = True
            # Assign scale factors for the different modes to display data rationally
            if self.data_mode in ic_modes:
                self.command_scale_factor = 1e12
                self.command_units = 'pA'
            elif self.data_mode in vc_modes:
                self.command_units = 'mV'
                self.command_scale_factor = 1e3
            else:  # data mode not known; plot as voltage
                self.command_units = 'V'
                self.command_scale_factor = 1.0
            if pars['limits']:
                cval = self.command_scale_factor * sequence_values[i]
                cmin = pars['cmin']
                cmax = pars['cmax']
                if cval < cmin or cval > cmax:
                    continue  # skip adding the data to the arrays

            self.devicesUsed = getDevices(data_dir_handle)
            self.clampDevices = getClampDeviceNames(data_dir_handle)
            self.holding = getClampHoldingLevel(data_file_handle)
            self.amplifierSettings = getWCCompSettings(data_file_handle)
            self.clampState = getClampState(data_file_handle)
            # print self.devicesUsed
            cmd = getClampCommand(data_file)

            data = getClampPrimary(data_file)
            # store primary channel data and read command amplitude
            info1 = data.infoCopy()
            # we need to handle all the various cases where the data is stored in different parts of the
            # "info" structure
            if 'startTime' in info1[0].keys():
                start_time = info1[0]['startTime']
            elif 'startTime' in info1[1].keys():
                start_time = info1[1]['startTime']
            elif 'startTime' in info1[1]['DAQ']['command'].keys():
                start_time = info1[1]['DAQ']['command']['startTime']
            else:
                start_time = 0.0
            self.trace_StartTimes = np.append(self.trace_StartTimes, start_time)
            traces.append(data.view(np.ndarray))
            cmd_wave.append(cmd.view(np.ndarray))
            # pick up and save the sequence values
            if len(sequence_values) > 0:
                self.values.append(sequence_values[i])
            else:
                self.values.append(cmd[len(cmd) / 2])
        if traces is None or len(traces) == 0:
            print "PatchEPhys/GetClamps: No data found in this run..."
            return None
        self.RSeriesUncomp = 0.
        if self.amplifierSettings['WCCompValid']:
            if self.amplifierSettings['WCEnabled'] and self.amplifierSettings['CompEnabled']:
                self.RSeriesUncomp= self.amplifierSettings['WCResistance'] * (1.0 - self.amplifierSettings['CompCorrection'] / 100.)
            else:
                self.RSeriesUncomp = 0.

        # put relative to the start
        self.trace_StartTimes -= self.trace_StartTimes[0]
        traces = np.vstack(traces)
        self.cmd_wave = np.vstack(cmd_wave)
        self.time_base = np.array(cmd.xvals('Time'))
        self.commandLevels = np.array(self.values)
        # set up the selection region correctly and
        # prepare IV curves and find spikes
        info = [
            {'name': 'Command', 'units': cmd.axisUnits(-1),
             'values': np.array(self.values)},
            data.infoCopy('Time'),
            data.infoCopy(-1)]
        traces = traces[:len(self.values)]
        self.traces = MetaArray(traces, info=info)
#        sfreq = self.dataModel.getSampleRate(data_file_handle)
        self.sample_interval = 1. / getSampleRate(data_file_handle)
        vc_command = data_dir_handle.parent().info()['devices'][self.clampDevices[0]]
        self.tstart = 0.01
        self.tdur = 0.5
        self.tend = 0.510
        # print 'vc_command: ', vc_command.keys()
        # print vc_command['waveGeneratorWidget'].keys()
        if 'waveGeneratorWidget' in vc_command.keys():
            # print 'wgwidget'
            try:
                vc_info = vc_command['waveGeneratorWidget']['stimuli']['Pulse']
                # print 'stimuli/Pulse'
                pulsestart = vc_info['start']['value']
                pulsedur = vc_info['length']['value']
            except KeyError:
                try:
                    vc_info = vc_command['waveGeneratorWidget']['function']
                    # print 'function'
                    pulse = vc_info[6:-1].split(',')
                    pulsestart = eval(pulse[0])
                    pulsedur = eval(pulse[1])
                except:
                    raise Exception('WaveGeneratorWidget not found')
                    pulsestart = 0.
                    pulsedur = np.max(self.time_base)
        elif 'daqState' in vc_command:
            # print 'daqstate'
            vc_state = vc_command['daqState']['channels']['command']['waveGeneratorWidget']
            func = vc_state['function']
            if func == '':  # fake values so we can at least look at the data
                pulsestart = 0.01
                pulsedur = 0.001
            else:  # regex parse the function string: pulse(100, 1000, amp)
                pulsereg = re.compile("(^pulse)\((\d*),\s*(\d*),\s*(\w*)\)")
                match = pulsereg.match(func)
                g = match.groups()
                if g is None:
                    raise Exception('PatchEPhys/GetClamps cannot parse waveGenerator function: %s' % func)
                pulsestart = float(g[1]) / 1000.  # values coming in are in ms, but need s
                pulsedur = float(g[2]) / 1000.
        else:
            raise Exception("PatchEPhys/GetClamps: cannot find pulse information")
        # adjusting pulse start/duration is necessary for early files, where the values
        # were stored as msec, rather than sec. 
        # we do this by checking the values against the time base itself, which is always in seconds.
        # if they are too big, we guess (usually correctly) that the values are in the wrong units
        if pulsestart + pulsedur > np.max(self.time_base):
            pulsestart *= 1e-3
            pulsedur *= 1e-3
        cmdtimes = np.array([pulsestart, pulsedur])
        if pars['KeepT'] is False:  # update times with current times.
            self.tstart = cmdtimes[0]  # cmd.xvals('Time')[cmdtimes[0]]
            self.tend = np.sum(cmdtimes)  # cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart
        clampInfo['PulseWindow'] = [self.tstart, self.tend, self.tdur]
#        print 'start/end/dur: ', self.tstart, self.tend, self.tdur
        # build the list of command values that are used for the fitting
        clampInfo['cmdList'] = []
        for i in range(len(self.values)):
            clampInfo['cmdList'].append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))

        if self.data_mode in vc_modes:
            self.spikecount = np.zeros(len(np.array(self.values)))
        return clampInfo

    def getParsDefaults(self, pars):
        """
        pars is a dictionary that defines the special cases for getClamps. 
        Here, given the pars dictionary that was passed to getClamps, we make sure that all needed
        elements are present, and substitute logical values for those that are missing
        :returns: updated pars dictionary
        """
        
        if pars is None:
            pars = {}
        # neededKeys = ['limits', 'cmin', 'cmax', 'KeepT', 'sequence1', 'sequence2']
        # hmm. could do this as a dictionary of value: default pairs and a loop
        k = pars.keys()
        if 'limits' not in k:
            pars['limits'] = False 
        if 'cmin' not in k:
            pars['cmin'] = -np.inf 
            pars['cmax'] = np.inf
        if 'KeepT' not in k:
            pars['KeepT'] = False 
        # sequence selections:
        # pars[''sequence'] is a dictionary
        # The dictionary has  'index' (currentIndex()) and 'count' from the GUI
        if 'sequence1' not in k:
            pars['sequence1'] = {'index': 0}  # index of '0' is "All"
            pars['sequence1']['count'] = 0 
        if 'sequence2' not in k:
            pars['sequence2'] = {'index': 0} 
            pars['sequence2']['count'] = 0
        return pars
        

