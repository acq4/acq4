from __future__ import annotations

from ._base import PatchPipetteState


class FouledState(PatchPipetteState):
    stateName = 'fouled'
    _parameterDefaultOverrides = {
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': True,
    }

    def initialize(self):
        self.dev.setTipClean(False)
        super().initialize()
