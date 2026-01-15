from acq4.util.mies import MIES
from .patchclamp import MIESPatchClamp
from .pressure_control import MIESPressureControl
from ..PatchPipette import PatchPipette


class MIESPatchPipette(PatchPipette):
    """A single patch pipette channel that uses a running MIES instance to handle
    electrophysiology and pressure control.
    """

    def __init__(self, deviceManager, config, name):
        self.mies = MIES.getBridge()
        self._headstage = config.pop('headstage')

        # create pressure and clamp devices
        clampName = f"{name}_clamp"
        self._mies_clamp = MIESPatchClamp(
            deviceManager, config={'headstage': self._headstage}, name=clampName
        )

        pressureName = f"{name}_pressure"
        self._mies_pressure = MIESPressureControl(
            deviceManager, config={'headstage': self._headstage}, name=pressureName
        )

        config.update({'clampDevice': clampName, 'pressureDevice': pressureName})
        super().__init__(deviceManager, config, name)

    def setActive(self, active):
        self.mies.setHeadstageActive(self._headstage, active)
        PatchPipette.setActive(self, active)

    def setSelected(self):
        self.mies.selectHeadstage(self._headstage)
