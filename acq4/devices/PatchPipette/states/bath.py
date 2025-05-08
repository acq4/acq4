from __future__ import annotations

import numpy as np

from ._base import PatchPipetteState


class BathState(PatchPipetteState):
    """Handles detection of changes while in recording chamber

    - monitor resistance to detect entry into bath
    - auto pipette offset and record initial resistance
    - monitor resistance for pipette break / clog

    Parameters
    ----------
    bathThreshold : float
        Resistance (Ohms) below which the tip is considered to be immersed in the bath (default: 50 MOhm).
    bathPressure : float
        Pressure (Pa) to apply once in the bath solution (default: 1.5kPa).
    breakThreshold : float
        Threshold for change in resistance (Ohms) for detecting a broken pipette (default: -1 MOhm).
    clogThreshold : float
        Threshold for change in resistance (Ohms) for detecting a clogged pipette (default: 1 MOhm).
    """

    stateName = 'bath'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    _parameterDefaultOverrides = {
        'initialPressure': 3500.0,  # 0.5 PSI
        'initialPressureSource': 'regulator',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialICHolding': 0,
        'initialTestPulseEnable': True,
    }
    _parameterTreeConfig = {
        'bathThreshold': {'type': 'float', 'default': 50e6, 'suffix': 'Ω'},
        'bathPressure': {'type': 'float', 'default': 1500, 'suffix': 'Pa'},
        'breakThreshold': {'type': 'float', 'default': -1e6, 'suffix': 'Ω'},
        'clogThreshold': {'type': 'float', 'default': 1e6, 'suffix': 'Ω'},
    }

    def run(self):
        self.monitorTestPulse()
        config = self.config
        dev = self.dev
        initialResistance = None
        at_initial_pressure = True
        bathResistances = []

        while True:
            self.checkStop()

            # pull in all new test pulses (hopefully only one since the last time we checked)
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            tp = tps[-1]  # if we're falling behind, just skip the extra test pulses

            ssr = tp.analysis['steady_state_resistance']
            if ssr > config['bathThreshold']:
                # not in bath yet
                bathResistances = []
                continue

            if at_initial_pressure:
                dev.pressureDevice.setPressure('regulator', config['bathPressure'])
                at_initial_pressure = False

            bathResistances.append(ssr)

            if initialResistance is None:
                if len(bathResistances) > 8:
                    initialResistance = np.median(bathResistances)
                    self.setState(f"initial resistance measured: {initialResistance * 1e-6:0.2f} MOhm")

                    # record initial resistance
                    patchrec = dev.patchRecord()
                    patchrec['initialBathResistance'] = initialResistance
                    piprec = dev.pipetteRecord()
                    if piprec['originalResistance'] is None:
                        piprec['originalResistance'] = initialResistance
                        patchrec['originalPipetteResistance'] = initialResistance

                else:
                    continue

            # check for pipette break
            if config['breakThreshold'] is not None and (ssr < initialResistance + config['breakThreshold']):
                self.setState('broken pipette detected')
                self._taskDone(interrupted=True, error="Pipette broken")
                return 'broken'

            # if close to target, switch to cell detect
            # pos = dev.globalPosition()
            # target = dev.
            if config['clogThreshold'] is not None and (ssr > initialResistance + config['clogThreshold']):
                self.setState('clogged pipette detected')
                self._taskDone(interrupted=True, error="Pipette clogged")
                return 'fouled'
