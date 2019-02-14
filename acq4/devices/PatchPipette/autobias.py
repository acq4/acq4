import scipy.stats
import numpy as np
from acq4.pyqtgraph import ptime
import acq4.pyqtgraph as pg


class AutoBiasHandler(object):
    """Implements automatic current clamp bias targeting a specific membrane potential.
    """
    def __init__(self, pip, **kwds):
        self.pip = pip
        self.params = {
            'enabled': False,
            'targetPotential': -70e-3,
            'followRate': 0.3,
            'minCurrent': -1.5e-9,
            'maxCurrent': 1.5e-9,
        }
        self.results = []
        self.setParams(**kwds)

    def setParams(self, **kwds):
        pg.disconnect(self.pip.sigTestPulseFinished, self.testPulseFinished)
        for k,v in kwds.items():
            if k not in self.params:
                raise NameError('Unknown parameter "%s"' % k)
            self.params[k] = v
        
        if self.params['enabled'] is True:
            self.pip.sigTestPulseFinished.connect(self.testPulseFinished)

    def getParam(self, param):
        return self.params[param]

    def testPulseFinished(self, pip, result):
        mode = result.clampMode()
        if mode.lower() != 'ic':
            return
        
        self.results.append(result)

        now = ptime.time()
        while len(self.results) > 1 and self.results[0].startTime() < now - 10.0:
            self.results.pop(0)

        self.updateHolding()

    def updateHolding(self):
        analyses = [result.analysis() for result in self.results]
        rm = np.median([analysis['steadyStateResistance'] for analysis in analyses])
        rm = np.clip(rm, 1e6, 10e9)

        vm = analyses[-1]['baselinePotential']
        dv = self.params['targetPotential'] - vm
        di = dv / rm        

        mode = self.results[0].clampMode()
        holding = self.pip.clampDevice.getHolding(mode)
        newHolding = holding + di * self.params['followRate']
        newHolding = np.clip(newHolding, self.params['minCurrent'], self.params['maxCurrent'])

        self.pip.clampDevice.setHolding(mode, newHolding)
