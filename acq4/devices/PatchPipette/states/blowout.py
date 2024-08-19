from __future__ import annotations

from acq4.util import ptime
from acq4.util.debug import printExc
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
            self.waitFor(fut, timeout=None)

        self.dev.pressureDevice.setPressure(source='regulator', pressure=config['blowoutPressure'])
        self.sleep(config['blowoutDuration'])
        self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        # wait until we have a test pulse that ran after blowout was finished.
        start = ptime.time()
        while True:
            self.checkStop()
            tps = self.getTestPulses(timeout=0.2)
            if len(tps) == 0 or tps[-1].start_time < start:
                continue
            break

        tp = tps[-1].analysis
        patchrec['resistanceAfterBlowout'] = tp['steady_state_resistance']
        self.dev.finishPatchRecord()
        return config['fallbackState']

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after blowout")
        super().cleanup()
