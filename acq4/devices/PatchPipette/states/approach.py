from __future__ import annotations

from ._base import PatchPipetteState


class ApproachState(PatchPipetteState):
    stateName = 'approach'

    _parameterDefaultOverrides = {
        'fallbackState': 'bath',
    }
    _parameterTreeConfig = {
        'nextState': {'type': 'str', 'default': 'cell detect'},
    }

    def run(self):
        # move to approach position + auto pipette offset
        fut = self.dev.pipetteDevice.goApproach('fast')
        self.dev.clampDevice.autoPipetteOffset()
        self.dev.clampDevice.resetTestPulseHistory()
        self.waitFor(fut, timeout=None)
        return self.config['nextState']
