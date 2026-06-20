from __future__ import annotations

from acq4.util.debug import log_and_ignore_exception
from acq4.util.task import asynch
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
        'nextState': 'out',
    }
    _parameterTreeConfig = {
        'cleanSequence': {'type': 'str', 'default': "[(-35e3, 1.0), (100e3, 1.0)] * 5"},  # TODO
        'rinseSequence': {'type': 'str', 'default': "[(-35e3, 3.0), (100e3, 10.0)]"},  # TODO
        'sonicationProtocol': {'type': 'str', 'default': 'clean'},
        'nextState': {'type': 'str', 'default': 'out'},
    }

    def __init__(self, *args, **kwds):
        self.sonication = None
        self.moveFuture = None
        self._moves_to_undo = []
        super().__init__(*args, **kwds)

    def run(self):
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

            site = pip.getSiteFor(stage)
            if site is not None:
                task1 = site.moveToInteract(pip, speed='fast')
            else:
                task1 = pip.moveTo(stage, "fast")
            task1.wait(60)

            if dev.sonicatorDevice is not None:
                self.sonication = dev.sonicatorDevice.doProtocol(config['sonicationProtocol'])

            for pressure, delay in sequence:
                dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
                self.sleep(delay)

            if self.sonication is not None and not self.sonication.is_done:
                self.sonication.wait(None)

        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        task2 = pip.goHome()
        task2.wait(None)
        dev.pipetteRecord()['cleanCount'] += 1
        dev.setTipClean(True)
        dev.newPatchAttempt()
        return {"state": config['nextState']}

    def _cleanup(self):
        with log_and_ignore_exception(Exception, "Error stopping sonication"):
            if self.sonication is not None and not self.sonication.is_done:
                self.sonication.stop("parent task is cleaning up before sonication finished")

        with log_and_ignore_exception(Exception, "Error resetting pressure after clean"):
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        super()._cleanup()
