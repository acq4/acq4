from ._base import PatchPipetteState


class OutsideOutState(PatchPipetteState):
    stateName = "outside out"

    _parameterDefaultOverrides = {
        'initialPressureSource': 'atmosphere',
        'initialClampMode': 'VC',
        'initialVCHolding': 0,
        'initialTestPulseEnable': False,
    }
