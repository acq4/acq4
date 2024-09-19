from __future__ import annotations

from ._base import PatchPipetteState


class BrokenState(PatchPipetteState):
    stateName = 'broken'
    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
        'finishPatchRecord': True,
    }

    def initialize(self):
        self.dev.setTipBroken(True)
        super().initialize()
