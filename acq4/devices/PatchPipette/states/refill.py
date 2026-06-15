# Patch pipette refill state: moves to refill site, sucks in internal solution, returns home.
# Supports periodic clog mitigation (pressure pulse and/or sonication) interleaved with suction.
from __future__ import annotations

from acq4.util.gentle import asynch, synch
from ._base import PatchPipetteState


class RefillState(PatchPipetteState):
    """Pipette refill state.

    Moves pipette to a named refill location, applies negative (suction) pressure to draw in
    internal solution, then returns home. Optionally interleaves periodic clog mitigation steps
    (a brief pressure pulse and/or sonication) throughout the refill period.

    Parameters
    ----------
    refillPressure : float
        Pressure (Pa) applied during suction phase. Should be negative (e.g. -20 kPa).
    refillDuration : float
        Total time (s) to spend at the refill site applying suction.
    clogMitigationInterval : float
        How often (s) to pause suction and run a clog mitigation step. 0 disables periodic
        mitigation (suction runs uninterrupted for the full refillDuration).
    clogMitigationPressure : float
        Pressure (Pa) applied during each clog mitigation step (typically positive).
    clogMitigationDuration : float
        Duration (s) of each clog mitigation pressure pulse.
    sonicationProtocol : str
        Protocol to pass to sonicatorDevice during each clog mitigation step. Empty string
        disables sonication.
    nextState : str
        State to transition to after refill completes.
    """

    stateName = 'refill'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': False,
        'fallbackState': 'out',
        'nextState': 'bath',
    }
    _parameterTreeConfig = {
        'refillPressure': {'type': 'float', 'default': -20e3, 'suffix': 'Pa'},
        'refillDuration': {'type': 'float', 'default': 180.0, 'suffix': 's'},
        'clogMitigationInterval': {'type': 'float', 'default': 30.0, 'suffix': 's'},
        'clogMitigationPressure': {'type': 'float', 'default': 10e3, 'suffix': 'Pa'},
        'clogMitigationDuration': {'type': 'float', 'default': 0.5, 'suffix': 's'},
        'sonicationProtocol': {'type': 'str', 'default': ''},
        'nextState': {'type': 'str', 'default': 'bath'},
    }

    def __init__(self, *args, **kwds):
        self._sonication = None
        super().__init__(*args, **kwds)

    def run(self):
        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.setState('refilling pipette')
        site = pip.getSiteFor('refill')
        if site is not None:
            self.waitFor(site.moveToInteract(pip, speed='fast'), timeout=60)
        else:
            self.waitFor(pip.moveTo('refill', 'fast'), timeout=60)

        refill_pressure = config['refillPressure']
        refill_duration = config['refillDuration']
        mitigation_interval = config['clogMitigationInterval']
        mitigation_pressure = config['clogMitigationPressure']
        mitigation_duration = config['clogMitigationDuration']
        sonication_protocol = config['sonicationProtocol']

        # If no interval configured, treat the whole duration as one block.
        if mitigation_interval <= 0:
            mitigation_interval = refill_duration

        remaining = refill_duration
        while remaining > 0:
            self.checkStop()
            chunk = min(remaining, mitigation_interval)
            dev.pressureDevice.setPressure(source='regulator', pressure=refill_pressure)
            self.sleep(chunk)
            remaining -= chunk

            if remaining > 0:
                self._runClogMitigation(dev, sonication_protocol, mitigation_pressure, mitigation_duration)

        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        self.waitFor(pip.goHome())
        dev.pipetteRecord()['refillCount'] = dev.pipetteRecord().get('refillCount', 0) + 1
        return {'state': config['nextState']}

    def _runClogMitigation(self, dev, sonication_protocol, pressure, duration):
        self.setState('clog mitigation')
        sonication = None
        if sonication_protocol and dev.sonicatorDevice is not None:
            sonication = dev.sonicatorDevice.doProtocol(sonication_protocol)
            self._sonication = sonication

        if pressure != 0:
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            self.sleep(duration)

        if sonication is not None and not sonication.is_done:
            self.waitFor(sonication)

        self.setState('refilling pipette')

    @asynch
    def _cleanup(self):
        dev = self.dev
        try:
            if self._sonication is not None and not self._sonication.is_done:
                self._sonication.stop("parent task is cleaning up before sonication finished")
        except Exception:
            dev.logger.exception("Error stopping sonication during refill cleanup")

        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            dev.logger.exception("Error resetting pressure after refill")

        synch(super()._cleanup)()
