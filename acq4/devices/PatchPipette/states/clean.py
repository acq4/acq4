from __future__ import annotations

import numpy as np

from acq4.util.future import Future, sleep
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
        # self.monitorTestPulse() # check for later to see if needed

        config = self.config.copy()
        dev = self.dev
        pip = dev.pipetteDevice

        self.set_state('cleaning')

        # for stage in ('clean', 'rinse'):
        #     self.checkStop()
        #
        #     sequence = config[f'{stage}Sequence']
        #     if isinstance(sequence, str):
        #         sequence = eval(sequence, units.__dict__)
        #     if len(sequence) == 0:
        #         continue
        #
        #
        #
        #     self.wait_for(pip.moveTo(stage, "fast"), timeout=30)
        #
        #     if dev.sonicatorDevice is not None:
        #         self.sonication = dev.sonicatorDevice.doProtocol(config['sonicationProtocol'])
        #
        #     for pressure, delay in sequence:
        #         dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
        #         self.sleep(delay)
        #
        #     if self.sonication is not None and not self.sonication.isDone():
        #         self.wait_for(self.sonication)

        sequence = config['cleanSequence']
        if isinstance(sequence, str):
            sequence = eval(sequence, units.__dict__)
        assert len(sequence) > 0

        scope = pip.imagingDevice().scopeDev
        start_pos = scope.globalPosition()
        waypoints = [
            (np.array([start_pos[0], start_pos[1], 30e-3]), "initial pos +3cm up"),
            (np.array([-90e-3, 20e-3, 30e-3]), "waaay out of the way"),
        ]
        for wp, name in waypoints:
            self.wait_for(scope.setGlobalPosition(wp, 20e-3, name=name))

        cw = pip.getCleaningWell()
        pip.retractFromSurface('fast')
        pip._moveToGlobal([0, 0, 10e-3], 'fast', name='safe position before cleaning well')
        self.wait_for(Future(cw.moveToInteract, (pip,)), timeout=60)

        if dev.sonicatorDevice is not None:
            self.sonication = Future(dev.sonicatorDevice.doProtocol, (config['sonicationProtocol'],))

        for pressure, delay in sequence:
            dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
            sleep(delay)

        if self.sonication is not None and not self.sonication.is_done:
            self.wait_for(self.sonication)

        self.wait_for(Future(cw.moveToApproach, (pip,)))

        dev.pressureDevice.setPressure(source='atmosphere', pressure=0)

        # self.wait_for(pip.moveTo('home', 'fast'))  # motion planning doesn't work so well from here
        self.wait_for(pip.parentStage.goHome('fast'))
        waypoints = waypoints[::-1] + [(start_pos, "initial pos")]
        for wp, name in waypoints:
            self.wait_for(scope.setGlobalPosition(wp, 20e-3, name=name))

        # TODO this could have worked...
        # cw = pip.getCleaningWell()
        # self.wait_for(cw.moveToInteract(pip), timeout=60)
        #
        # if dev.sonicatorDevice is not None:
        #     self.sonication = dev.sonicatorDevice.doProtocol(config['sonicationProtocol'])
        #
        # for pressure, delay in sequence:
        #     dev.pressureDevice.setPressure(source='regulator', pressure=pressure)
        #     self.sleep(delay)
        #
        # if self.sonication is not None and not self.sonication.isDone():
        #     self.wait_for(self.sonication)
        #
        # self.wait_for(cw.moveToApproach(pip))
        #
        # dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        #
        # self.wait_for(pip.parentStage.goHome('fast'))
        # self.wait_for(cw._unwindKludgePath(pip))

        dev.pipetteRecord()['cleanCount'] += 1
        dev.setTipClean(True)
        self.currentFuture = None
        dev.newPatchAttempt()
        return {"state": config['nextState']}

    def resetPosition(self, parent_future):
        # todo we need to handle this somehow for both path generators
        if self.moveFuture is not None:
            fut = self.moveFuture.undo()
            self.moveFuture = None
            parent_future.wait_for(fut, timeout=None)

    def _cleanup(self):
        dev = self.dev
        try:
            if self.sonication is not None and not self.sonication.is_done:
                self.sonication.stop("parent task is cleaning up before sonication finished")
        except Exception:
            dev.logger.exception("Error stopping sonication")

        try:
            dev.pressureDevice.setPressure(source='atmosphere', pressure=0)
        except Exception:
            dev.logger.exception("Error resetting pressure after clean")

        super()._cleanup()
