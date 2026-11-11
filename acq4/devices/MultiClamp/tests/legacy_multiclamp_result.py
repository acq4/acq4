"""Frozen copy of the original MultiClampTask.getResult: the test oracle."""
import numpy as np

from MetaArray import MetaArray, axis


def legacyGetResult(self):
    ## Access data recorded from DAQ task
    ## create MetaArray and fill with MC state info
    channels = self.getUsedChannels()
    result = {}
    #result['info'] = self.state
    for ch in channels:
        chConf = self.dev.config[f'{ch}Channel']
        result[ch] = self.daqTasks[ch].getData(chConf['channel'])
        nPts = result[ch]['info']['numPts']
        rate = result[ch]['info']['rate']
        if ch == 'command':
            #result[ch]['data'] = result[ch]['data'] / self.dev.config['cmdScale'][self.cmd['mode']]
            result[ch]['data'] = result[ch]['data'] * self.state['extCmdScale']
            result[ch]['name'] = 'command'
            if self.cmd['mode'] == 'VC':
                result[ch]['units'] = 'V'
            else:
                result[ch]['units'] = 'A'
        else:
            #scale = 1.0 / self.state[ch + 'Signal'][1]
            scale = self.state[f'{ch}ScaleFactor']
            result[ch]['data'] = result[ch]['data'] * scale
            #result[ch]['units'] = self.state[ch + 'Signal'][2]
            result[ch]['units'] = self.state[f'{ch}Units']
            result[ch]['name'] = ch

    if len(result) == 0:
        return None

    daqState = {ch: result[ch]['info'] for ch in result}
    ## record command holding value
    if 'command' not in daqState:
        daqState['command'] = {}
    daqState['command']['holding'] = self.holdingVal

    #timeVals = linspace(0, float(self.state['numPts']-1) / float(self.state['rate']), self.state['numPts'])
    timeVals = np.linspace(0, float(nPts-1) / float(rate), nPts)
    chanList = [np.atleast_2d(result[x]['data']) for x in result]
    # for l in chanList:
    cols = [(result[x]['name'], result[x]['units']) for x in result]
    try:
        arr = np.concatenate(chanList)
    except:
        for a in chanList:
            print(a.shape)
        raise

    info = [axis(name='Channel', cols=cols), axis(name='Time', units='s', values=timeVals)] + [{'ClampState': self.state, 'DAQ': daqState}]

    taskInfo = self.cmd.copy()
    if 'command' in taskInfo:
        del taskInfo['command']
    info[-1]['Protocol'] = taskInfo
    info[-1]['startTime'] = result[list(result.keys())[0]]['info']['startTime']

    return MetaArray(arr, info=info)
