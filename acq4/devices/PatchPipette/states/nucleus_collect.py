from __future__ import annotations

from acq4.util.debug import printExc
from pyqtgraph import units
from ._base import PatchPipetteState


class NucleusCollectState(PatchPipetteState):
    """Nucleus collection state.

    Cycles +/- pressure in a nucleus collection tube.

    Parameters
    ----------
    pressureSequence : list
        List of (pressure (Pa), duration (s)) pairs specifying how to pulse pressure while the pipette tip is in the
        cleaning well.
    approachDistance : float
        Distance (m) from collection location to approach from.
    """
    stateName = 'collect'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialTestPulseEnable': False,
        'fallbackState': 'out',
    }
    _parameterTreeConfig = {
        'pressureSequence': {'type': 'str', 'default': "[(60e3, 4.0), (-35e3, 1.0)] * 5"},
        'approachDistance': {'type': 'float', 'default': 30e-3, 'suffix': 's'},
    }

    def __init__(self, *args, **kwds):
        self.currentFuture = None
        super().__init__(*args, **kwds)

    def run(self):
        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.setState('nucleus collection')

        # move to top of collection tube
        self.startPos = pip.globalPosition()
        self.collectionPos = pip.loadPosition('collect')
        # self.approachPos = self.collectionPos - pip.globalDirection() * config['approachDistance']

        # self.waitFor([pip._moveToGlobal(self.approachPos, speed='fast')])
        self.waitFor(pip._moveToGlobal(self.collectionPos, speed='fast'), timeout=None)

        sequence = config['pressureSequence']
        if isinstance(sequence, str):
            sequence = eval(sequence, units.__dict__)

        for pressure, delay in sequence:
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            self.checkStop(delay)

        dev.pipetteRecord()['expelled_nucleus'] = True
        return 'out'

    def resetPosition(self):
        pip = self.dev.pipetteDevice
        # self.waitFor([pip._moveToGlobal(self.approachPos, speed='fast')])
        self.waitFor(pip._moveToGlobal(self.startPos, speed='fast'), timeout=None)

    def cleanup(self):
        dev = self.dev
        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            printExc("Error resetting pressure after collection")

        self.resetPosition()
        super().cleanup()
