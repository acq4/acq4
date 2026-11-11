"""Frozen copy of the original DAQGenericTask.getResult: the test oracle."""
from collections import OrderedDict
from typing import Optional

import numpy as np

from MetaArray import MetaArray, axis


def legacyGetResult(self) -> Optional[MetaArray]:
    ## Access data recorded from DAQ task
    ## create MetaArray and fill with MC state info

    ## Collect data and info for each channel in the command
    result = {}
    for ch in self.bufferedChannels:
        result[ch] = self.daqTasks[ch].getData(self.dev._DGConfig[ch]['channel'])
        result[ch]['data'] = self.mapping.mapFromDaq(ch, result[ch]['data'])  ## scale/offset/invert
        result[ch]['units'] = self.getChanUnits(ch)

    if len(result) <= 0:
        return None
    meta = result[list(result.keys())[0]]['info']
    rate = meta['rate']
    nPts = meta['numPts']
    ## Create an array of time values
    timeVals = np.linspace(0, float(nPts - 1) / float(rate), nPts)

    ## Concatenate all channels together into a single array, generate MetaArray info
    chanList = [np.atleast_2d(result[x]['data']) for x in result]
    cols = [(x, result[x]['units']) for x in result]
    try:
        arr = np.concatenate(chanList)
    except Exception:
        print(chanList)
        print([a.shape for a in chanList])
        raise

    daqState = OrderedDict()
    for ch in self.dev._DGConfig:
        if ch in result:
            daqState[ch] = result[ch]['info']
        else:
            daqState[ch] = {}

        ## record current holding value for all output channels (even those that were not buffered for this task)    
        if self.dev._DGConfig[ch]['type'] in ['ao', 'do']:
            daqState[ch]['holding'] = self.holdingVals[ch]

    info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [
        {'DAQ': daqState}]

    protInfo = self._DAQCmd.copy()  ## copy everything but the command arrays and low-level configuration info
    for ch in protInfo:
        protInfo[ch].pop('command', None)
        protInfo[ch].pop('lowLevelConf', None)
    info[-1]['Protocol'] = protInfo

    return MetaArray(arr, info=info)
