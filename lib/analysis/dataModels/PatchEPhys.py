# -*- coding: utf-8 -*-
import DataManager
import SequenceRunner
from advancedTypes import OrderedDict
import functools

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


class DataModel:
    """Class for formalizing the raw data structures used in analysis.
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
        Objects may have multiple types (ie protocol seq and photostim scan)
        An instance of this class refers to any piece of data, but most commonly will refer to a directory or file.
        
    """
    def __init__(self):
        pass
    
    
    def isSequence(self, dh):
        """Return true if dh is a directory handle for a protocol sequence."""
        return dirType(dh) == 'ProtocolSequence'
        #if 'sequenceParams' in dh.info():
            #return True
        #else:
            #return False
        
    def dirType(self, dh):
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
                    if self.dirType(dh.parent()) == 'ProtocolSequence':
                        type = 'Protocol'
                    else:
                        raise Exception()
                except:
                    raise Exception("Can't determine type for dir %s" % dh.name())
        return type
    
    def listSequenceParams(self, dh):
        """Given a directory handle for a protocol sequence, return the dict of sequence parameters"""
        try:
            return dh.info()['sequenceParams']
        except KeyError:
            raise Exception("Directory '%s' does not appear to be a protocol sequence." % dh.name())
    
    def buildSequenceArray(self, dh, func):
        """Builds a MetaArray of data compiled across a sequence. 
        Arguments:
          dh:   directory handle for the protocol sequence
          func: a function that returns an array or scalar, given a protocol dir handle.
          
        Example: Return an array of all primary-channel clamp recordings across a sequence 
          buildSequenceArray(seqDir, lambda protoDir: getClampFile(protoDir).read()['primary'])"""
        params = self.listSequenceParams(dh)
        inds = OrderedDict([(k, range(len(v))) for k,v in params.iteritems()])
        def runFunc(dh, func, params):
            name = '_'.join(['%03d'%n for n in params.values()])
            fh = dh[name]
            return func(fh)
        data = SequenceRunner.runSequence(functools.partial(runFunc, dh, func), inds, inds.keys())
        return data
    
    
    def getClampFile(self, protoDH):
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
    
    def _isClampFile(self, fh):
        if fh.shortName() not in deviceNames['Clamp'] and fh.shortName()[:-3] not in deviceNames['Clamp']:
            return False
        else:
            return True
        
        
    def getClampMode(self, fh):
        """Given a clamp file handle, return the recording mode."""
        if not self._isClampFile(fh):
            raise Exception('%s not a clamp file.' %fh.shortName())
        
        data = fh.read()
        info = data._info[-1]
        
        if 'ClampState' in info:
            return info['ClampState']['mode']
        else:
            try:
                mode = info['mode']
                return mode
            except KeyError:
                return None
    
    def getClampHoldingLevel(self, fh):
        """Given a clamp file handle, return the holding level (voltage for VC, current for IC)."""
        
        if not self._isClampFile(fh):
            raise Exception('%s not a clamp file.' %fh.shortName())
        
        data = fh.read()
        info = data._info[-1]
        sinfo = fh.parentDir.info()
        
        if 'ClampState' in info:
            return info['ClampState']['holding']
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
            
    def getDayInfo(self, dh):
        while self.dirType(dh) != 'Day':
            dh = dh.parent()
        return dh.info()
    
    def getCellInfo(self, dh):
        while self.dirType(dh) not in ['Cell']:
            dh = dh.parent()
        return dh.info()
    
    def getACSF(self, dh):
        dayInfo = self.getDayInfo(dh)
        return dayInfo.get('solution', '')
        
    def getInternalSoln(self, dh):
        dayInfo = self.getDayInfo(dh)
        return dayInfo.get('internal', '')
    
    def getTemp(self, dh):
        if dh.isFile():
            dh = dh.parent()
        temp = dh.info().get(('Temperature','BathTemp'), None)
        if temp == None:
            temp = self.getDayInfo(dh).get('temperature', '')
        return temp
    
    def getCellType(self, dh):
        cellInfo = self.getCellInfo(dh)
        return cellInfo.get('type', '')
    
        

