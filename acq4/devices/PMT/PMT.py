# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.DAQGeneric import DAQGeneric

class PMT(DAQGeneric, OptomechDevice):
    """
    A photomultiplier tube (PMT) device for light detection.
    
    This device combines DAQGeneric for data acquisition with OptomechDevice 
    for optical positioning and transformations.
    
    Configuration options:
    
    * **channels** (dict): DAQ channel definitions (see DAQGeneric for format)
        - Input: Analog input channel for PMT signal
        - PlateVoltage: Optional analog input for plate voltage monitoring
    
    * **parentDevice** (str, optional): Name of parent optical device (microscope, etc.)
    
    * **transform** (dict, optional): Spatial transform relative to parent device
        - pos: Position offset [x, y] or [x, y, z]
        - scale: Scale factors [x, y] or [x, y, z] 
        - angle: Rotation angle in radians
    
    Example configuration::
    
        PMT:
            driver: 'PMT'
            parentDevice: 'Microscope'
            channels:
                Input:
                    device: 'DAQ'
                    channel: '/Dev1/ai0'
                    type: 'ai'
                PlateVoltage:
                    device: 'DAQ'
                    channel: '/Dev1/ai1'
                    type: 'ai'
    """
    def __init__(self, dm, config, name):
        self.omConf = {}
        for k in ['parentDevice', 'transform']:
            if k in config:
                self.omConf[k] = config.pop(k)
        DAQGeneric.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

    def getFilterDevice(self):
        # return parent filter device or None
        if 'Filter' in self.omConf.get('parentDevice', {}):
            return self.omConf['parentDevice']
        else:
            return None
        
        
