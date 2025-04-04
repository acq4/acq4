from __future__ import annotations

from acq4.util.debug import printExc
from acq4.util.future import future_wrap
from pyqtgraph import units
from ._base import PatchPipetteState


class CleanState(PatchPipetteState):
    """Pipette cleaning state.

    Cycles +/- pressure in a "clean" bath followed by an optional "rinse" bath.

    Parameters
    ----------
    cleanSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        cleaning well.
    rinseSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        rinse well.
    approachHeight : float
        Distance (m) above the clean/rinse wells to approach from. This is needed to ensure the pipette avoids the well
        walls when approaching.
    sonicationProtocol : str
        Protocol to use for sonication (default "clean"), or if supported, the full protocol definition for a custom
        protocol.
    """
    stateName = 'clean'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': False,
        'fallbackState': 'out',
        'finishPatchRecord': True,
    }
    _parameterTreeConfig = {
        'cleanSequence': {'type': 'str', 'default': "[(-35e3, 1.0), (100e3, 1.0)] * 5"},  # TODO
        'rinseSequence': {'type': 'str', 'default': "[(-35e3, 3.0), (100e3, 10.0)]"},  # TODO
        'approachHeight': {'type': 'float', 'default': 5e-3, 'suffix': 'm'},
        'sonicationProtocol': {'type': 'str', 'default': 'clean'},
    }

    def __init__(self, *args, **kwds):
        self.currentFuture = None
        self.sonication = None
        super().__init__(*args, **kwds)

    def run(self):
        # self.monitorTestPulse() # check for later to see if needed

        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.setState('cleaning')

        for stage in ('clean', 'rinse'):
            self.checkStop()

            sequence = config[f'{stage}Sequence']
            if isinstance(sequence, str):
                sequence = eval(sequence, units.__dict__)
            if len(sequence) == 0:
                continue

            self.currentFuture = pip.moveTo(stage, "fast")

            # todo: if needed, we can check TP for capacitance changes here
            # and stop moving as soon as the fluid is detected
            self.waitFor(self.currentFuture, timeout=None)

            if dev.sonicatorDevice is not None:
                self.sonication = dev.sonicatorDevice.doProtocol(config['sonicationProtocol'])

            for pressure, delay in sequence:
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                self.sleep(delay)

            if self.sonication is not None and not self.sonication.isDone():
                self.waitFor(self.sonication)

        pip.moveTo('home', 'fast').raiseErrors("trying to return home")
        dev.pipetteRecord()['cleanCount'] += 1
        dev.setTipClean(True)
        self.currentFuture = None
        dev.newPatchAttempt()
        return 'out'

    @future_wrap
    def cleanup(self, _future):
        try:
            if self.sonication is not None and not self.sonication.isDone():
                self.sonication.stop("parent task is cleaning up before sonication finished")
        except Exception:
            printExc("Error stopping sonication")

        try:
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after clean")

        _future.waitFor(self.dev.pipetteDevice.moveTo('home', 'fast'))
