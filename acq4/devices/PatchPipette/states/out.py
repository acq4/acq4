from __future__ import annotations

from ._base import PatchPipetteState


class OutState(PatchPipetteState):
    stateName = 'out'

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': False,
        'finishPatchRecord': True,
    }
