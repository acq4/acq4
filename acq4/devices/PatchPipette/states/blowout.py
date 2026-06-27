from __future__ import annotations

from gentletask import check_stop

from acq4.util import ptime
from acq4.util.debug import log_and_ignore_exception
from acq4.util.task import sleep
from ._base import PatchPipetteState


class BlowoutState(PatchPipetteState):
    stateName = 'blowout'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'blowoutPressure': {'type': 'float', 'default': 65e3, 'suffix': 'Pa'},
        'blowoutDuration': {'type': 'float', 'default': 2.0, 'suffix': 'Pa'},
    }

    def run(self):
        patchrec = self.dev.patchRecord()
        self.monitorTestPulse()
        config = self.config

        fut = self.dev.pipetteDevice.retractFromSurface()
        if fut is not None:
            fut.wait(None)

        self.dev.pressureDevice.setPressure(source='regulator', pressure=config['blowoutPressure'])
        duration = config['blowoutDuration']
        sleep(duration)
        self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        # wait until we have a test pulse that ran after blowout was finished.
        start = ptime.time()
        while True:
            check_stop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0 or tps[-1].start_time < start:
                continue
            break

        tp = tps[-1].analysis
        patchrec['resistanceAfterBlowout'] = tp['steady_state_resistance']
        self.dev.finishPatchRecord()
        return {"state": config['fallbackState']}

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error resetting pressure after blowout"):
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        super()._cleanup()
