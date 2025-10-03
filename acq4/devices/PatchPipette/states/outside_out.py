from ._base import PatchPipetteState


class OutsideOutState(PatchPipetteState):
    stateName = "outside out"

    _parameterDefaultOverrides = {
        'initialPressure': -0.5e3,
        'initialPressureSource': 'regulator',
        'initialClampMode': 'VC',
        'initialVCHolding': -55e-3,
        'initialTestPulseEnable': True,
    }
