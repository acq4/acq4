from __future__ import annotations

import numpy as np
from gentletask import check_stop

from acq4.util import ptime
from ._base import PatchPipetteState, exponential_decay_avg


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
    breakInMonitorTau : float
        Time constant (seconds) for exponential averaging of capacitance measurements when
        determining whether the cell has spontaneously broken in. Test pulses report NaN
        capacitance when there is no membrane transient to fit, which is counted as zero here, so
        this constant sets how long a real capacitance must persist before it is believed.
        Default 3s.
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
        'breakInMonitorTau': {'type': 'float', 'default': 3.0, 'suffix': 's'},
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
        ssr_avg = None
        delay = config['autoBreakInDelay']
        while True:
            if delay is not None and ptime.time() - startTime > delay:
                return {"state": 'break in'}

            check_stop()

            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0:
                continue

            tp = tps[-1]
            holding = tp.analysis['baseline_current']
            if holding < self.config['holdingCurrentThreshold']:
                self.setState(
                    f'Spontaneous detachment: holding current {holding * 1e9:.2f}nA is below `holdingCurrentThreshold`.'
                )
                return {"state": config['spontaneousDetachmentState']}

            cap = tp.analysis['capacitance']
            dt = ptime.time() - last_measure
            last_measure += dt
            resistance_tau = 1  # seconds
            # A test pulse with no membrane transient to fit reports NaN rather than zero. That
            # is the normal reading for an intact seal, so it counts as "no capacitance" here;
            # letting it into the average would poison it permanently and silently disable
            # break-in detection for the rest of the state, leaving a cell that ruptured on its
            # own to be mistaken for one that detached.
            cap_for_avg = 0.0 if np.isnan(cap) else cap
            if cap_avg is None:
                cap_avg = cap_for_avg
            else:
                # Averaged in place rather than via exponential_decay_avg: an intact seal holds
                # this series at zero for minutes at a time, and that helper's ratio term
                # divides by the previous average.
                alpha = 1 - np.exp(-dt / config['breakInMonitorTau'])
                cap_avg = cap_avg * (1 - alpha) + cap_for_avg * alpha
            ssr = tp.analysis['steady_state_resistance']
            ssr_avg, _ = exponential_decay_avg(dt, ssr_avg, ssr, resistance_tau)
            if cap_avg > config['capacitanceThreshold'] and ssr_avg < config['minimumBreakInResistance']:
                patchrec['spontaneousBreakin'] = True
                return {"state": config['spontaneousBreakInState']}

            if ssr_avg < config['resistanceThreshold']:
                self.setState(
                    f'Spontaneous detachment: steady state resistance {ssr_avg / 1e6:.1f}MΩ dropped below `resistanceThreshold`.'
                )
                return {"state": config['spontaneousDetachmentState']}

            patchrec['resistanceBeforeBreakin'] = ssr
            patchrec['capacitanceBeforeBreakin'] = cap
