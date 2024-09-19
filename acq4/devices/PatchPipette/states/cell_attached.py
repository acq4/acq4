from __future__ import annotations

import numpy as np

from acq4.util import ptime
from ._base import PatchPipetteState


class CellAttachedState(PatchPipetteState):
    """Pipette in cell-attached configuration

    State name: "cell attached"

    - automatically transition to 'break in' after a delay
    - monitor for spontaneous break-in or loss of attached cell

    Parameters
    ----------
    autoBreakInDelay : float
        Delay time (seconds) before transitioning to 'break in' state. If None, then never automatically
        transition to break-in.
    capacitanceThreshold : float
        Capacitance (default 10pF) above which the pipette is considered to be whole-cell and immediately
        transitions to the 'break in' state (in case of partial break-in, we don't want to transition
        directly to 'whole cell' state).
    minimumBreakInResistance : float
        Minimum resistance (Ohms) to allow spontaneous break-in to occur. Default 1 GOhm.
    resistanceThreshold : float
        Steady state resistance threshold (default 100MΩ) below which the cell is considered to either be
        'spontaneousDetachmentState' or 'spontaneousBreakInState'.
    holdingCurrentThreshold : float
        Holding current (presumed negative) below which the cell is considered to be lost and the state goes
        to `spontaneousDetachmentState'. Default -1nA.
    spontaneousBreakInState : str
        Name of state to transition to when the membrane breaks in spontaneously. Default is 'break in' so
        that partial break-ins will be completed. Consider 'whole cell' to avoid break-in protocol.
    spontaneousDetachmentState : str
        Name of state to transition to when the pipette completely loses its seal. Default is 'fouled', but
        consider using 'seal' or 'cell detect' for a retry.
    """
    stateName = 'cell attached'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': -70e-3,
        'initialTestPulseEnable': True,
    }
    _parameterTreeConfig = {
        'autoBreakInDelay': {'type': 'float', 'default': None, 'optional': True, 'suffix': 's'},
        'capacitanceThreshold': {'type': 'float', 'default': 10e-12, 'suffix': 'F'},
        'minimumBreakInResistance': {'type': 'float', 'default': 1e9, 'suffix': 'Ω'},
        'holdingCurrentThreshold': {'type': 'float', 'default': -1e-9, 'suffix': 'A'},
        'resistanceThreshold': {'type': 'float', 'default': 500e6, 'suffix': 'Ω'},
        'spontaneousBreakInState': {'type': 'str', 'default': 'break in'},
        'spontaneousDetachmentState': {'type': 'str', 'default': 'fouled'},
    }

    def run(self):
        self.monitorTestPulse()
        patchrec = self.dev.patchRecord()
        config = self.config
        last_measure = startTime = ptime.time()
        cap_avg = None
        delay = config['autoBreakInDelay']
        while True:
            if delay is not None and ptime.time() - startTime > delay:
                return 'break in'

            self.checkStop()

            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            tp = tps[-1]
            holding = tp.analysis['baseline_current']
            if holding < self.config['holdingCurrentThreshold']:
                self._taskDone(interrupted=True, error='Holding current exceeded threshold.')
                return config['spontaneousDetachmentState']

            cap = tp.analysis['capacitance']
            dt = ptime.time() - last_measure
            last_measure += dt
            if cap_avg is None:
                cap_avg = tp.analysis['capacitance']
            cap_avg_tau = 1  # seconds
            cap_alpha = 1 - np.exp(-dt / cap_avg_tau)
            cap_avg = cap_avg * (1 - cap_alpha) + cap * cap_alpha
            ssr = tp.analysis['steady_state_resistance']
            if cap_avg > config['capacitanceThreshold'] and ssr < config['minimumBreakInResistance']:
                patchrec['spontaneousBreakin'] = True
                return config['spontaneousBreakInState']

            if ssr < config['resistanceThreshold']:
                self._taskDone(interrupted=True, error='Steady state resistance dropped below threshold.')
                return config['spontaneousDetachmentState']

            patchrec['resistanceBeforeBreakin'] = ssr
            patchrec['capacitanceBeforeBreakin'] = cap
