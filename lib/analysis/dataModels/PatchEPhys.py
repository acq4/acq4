# -*- coding: utf-8 -*-
import DataManager


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
        Shpuld be able to easily switch to a different data model
        Objects may have multiple types (ie protocol seq and photostim scan)
        An instance of this class refers to any piece of data, but most commonly will refer to a directory or file.
        
    """
    def __init__(self):
        pass
    
    
    def getClampFile(self, protoDH):
        """Given a protocol directory handle, return the clamp file handle within. 
        If there are multiple clamps, only the first is returned.
        Return None if no clamps are found."""
        files = protoDH.listFiles()
        names = deviceNames('Clamp')
        for n in names:
            if n in files or n+'.ma' in files:
                return protoDH[n]
        return None
    
    

