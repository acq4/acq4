"""Frozen copies of the original LaserTask.getResult and MockClampTask.getResult: test oracles.

Each calls the frozen DAQGenericTask.getResult where the original called DAQGenericTask.getResult.
"""
import numpy as np

from MetaArray import MetaArray
from acq4.devices.DAQGeneric.tests.legacy_daqgeneric_result import legacyGetResult
from acq4.devices.NiDAQ.nidaq import NiDAQ


def legacyLaserGetResult(self):
    ## getResult from DAQGeneric, then add in command waveform
    result = legacyGetResult(self)
    if result is None:
        return None
    
    arr = result.view(np.ndarray)
    
    daqInfo = result._info[-1]['DAQ']
    ## find DAQ info for any output channel
    for ch in ['shutter', 'qSwitch', 'pCell']:
        if ch in daqInfo:
            ds = daqInfo[ch].get('downsampling', 1)
            break
    
    if 'powerWaveform' in self.cmd:
        ## downsample power waveform to match other channels
        power = self.cmd['powerWaveform']
        if ds > 1:
            power = NiDAQ.meanResample(power, ds)
        arr = np.append(arr, power[np.newaxis, :], axis=0)
        
        #result = np.append(result, self.cmd['powerWaveform'][np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'power', 'units': 'W'})
    elif 'switchWaveform' in self.cmd:
        switch = self.cmd['switchWaveform']
        if ds > 1:
            switch = NiDAQ.meanResample(switch, ds)
        arr = np.append(arr, switch[np.newaxis, :], axis=0)
        #result = np.append(result, self.cmd['switchWaveform'][np.newaxis, :], axis=0)
        result._info[0]['cols'].append({'name': 'switch'})
    #elif 'power' in self.cmd:
        #arr = np.append(arr, self.cmd['power']['command'][np.newaxis, :], axis=0)
        #result._info[0]['cols'].append({'name': str(self.cmd['power']['type'])})
        
    info = {'currentPower': self.currentPower, 
            'expectedPower': self.expectedPower, 
            'requestedWavelength':self.cmd.get('wavelength', None), 
            'shutterMode':self.cmd['shutterMode'],
            'powerCheckRequested':self.cmd.get('checkPower', False),
            'pulsesCmd': self.cmd.get('pulses', None)
            }
          
    
    result._info[-1]['Laser'] = info
    
    result = MetaArray(arr, info=result._info)
    self.dev.lastResult = result
   
    return result


def legacyMockClampGetResult(self):
    result = legacyGetResult(self)
    result._info[-1]['startTime'] = next(iter(result._info[-1]['DAQ'].values()))['startTime']
    result._info[-1]['ClampState'] = self.ampState
    return result
