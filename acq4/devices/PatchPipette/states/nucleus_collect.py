from __future__ import annotations

from acq4.util.future import Future
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
    sonicationProtocol : str
        Protocol to use for sonication (default "expel"), or if supported, the full protocol definition for a custom
        protocol.
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
        'sonicationProtocol': {'type': 'str', 'default': 'expel'},
    }

    def __init__(self, *args, **kwds):
        self.currentFuture = None
        self.sonication = None
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
        pip._moveToGlobal(self.collectionPos, speed='fast', name=f"{pip.name()} move to nucleus collection position")

        if dev.sonicatorDevice is not None:
            self.sonication = Future(dev.sonicatorDevice.doProtocol, (config['sonicationProtocol'],))

        sequence = config['pressureSequence']
        if isinstance(sequence, str):
            sequence = eval(sequence, units.__dict__)

        for pressure, delay in sequence:
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            self.sleep(delay)

        if self.sonication is not None and not self.sonication.isDone():
            self.waitFor(self.sonication)

        dev.pipetteRecord()['expelled_nucleus'] = True
        return {"state": 'out'}

        # # current version using InteractionSite moveToInteract/unwindKludgePath:
        # well = pip.getNucleusDepositionWell()
        # self.waitFor(well.moveToInteract(pip))
        #
        # if dev.sonicatorDevice is not None:
        #     self.sonication = dev.sonicatorDevice.doProtocol(config['sonicationProtocol'])
        #
        # sequence = config['pressureSequence']
        # if isinstance(sequence, str):
        #     sequence = eval(sequence, units.__dict__)
        #
        # for pressure, delay in sequence:
        #     dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
        #     self.sleep(delay)
        #
        # if self.sonication is not None and not self.sonication.isDone():
        #     self.waitFor(self.sonication)
        #
        # dev.pipetteRecord()['expelled_nucleus'] = True
        # self.waitFor(well._unwindKludgePath(pip))
        # return {"state": 'out'}

    def resetPosition(self):
        pip = self.dev.pipetteDevice
        if self.isDone():
            pip._moveToGlobal(self.startPos, speed='fast', name='return to start position')

    def _cleanup(self):
        try:
            if self.sonication is not None and not self.sonication.isDone():
                self.sonication.stop("parent task is cleaning up before sonication finished")
        except Exception:
            self.dev.logger.exception("Error stopping sonication")

        try:
            self.dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            self.dev.logger.exception("Error resetting pressure after collection")

        try:
            self.resetPosition()
        except Exception:
            self.dev.logger.exception("Error resetting pipette position after collection")

        super()._cleanup()
