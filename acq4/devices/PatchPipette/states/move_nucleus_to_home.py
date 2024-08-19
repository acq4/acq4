from __future__ import annotations

from ._base import PatchPipetteState


class MoveNucleusToHomeState(PatchPipetteState):
    """State that moves the pipette to its home position while applying negative pressure.

    State name: home with nucleus

    Parameters
    ----------
    pressureLimit : float
        The smallest vacuum pressure (pascals, expected negative value) to allow during state.
    """
    stateName = "home with nucleus"
    _parameterDefaultOverrides = {
        'initialPressure': None,
        'initialPressureSource': 'regulator',
    }
    _parameterTreeConfig = {
        # for expected negative values, a maximum is the "smallest" magnitude:
        'pressureLimit': {'type': 'float', 'default': -3e3, 'suffix': 'Pa'},
        'positionName': {'type': 'str', 'default': 'extract'},
    }

    def run(self):
        self.waitFor(self.dev.pressureDevice.rampPressure(maximum=self.config['pressureLimit']), timeout=None)
        self.waitFor(self.dev.pipetteDevice.moveTo(self.config['positionName'], 'fast'), timeout=None)
        self.sleep(float("inf"))
