from acq4.util.mies import MIES
from .patch_clamp import MIESPatchClamp
from .pressure_control import MIESPressureControl
from .states import MIESPatchPipetteStateManager
from ..PatchPipette import PatchPipette

from acq4.util import Qt


class MIESPatchPipette(PatchPipette):
    """A single patch pipette channel that uses a running MIES instance to handle
    electrophysiology and pressure control.
    """
    defaultStateManagerClass = MIESPatchPipetteStateManager

    def __init__(self, deviceManager, config, name):
        self.mies = MIES.getBridge()
        self._headstage = config.pop('headstage')

        # create pressure and clamp devices
        clampName = f"{name}_clamp"
        self._mies_clamp = MIESPatchClamp(
            deviceManager, 
            config={'headstage': self._headstage},
            name=clampName)

        pressureName = f"{name}_pressure"
        self._mies_pressure = MIESPressureControl(
            deviceManager, 
            config={'headstage': self._headstage},
            name=pressureName)

        config.update({
            # 'clampDevice': clampName,  # for now, operate without a clamp device
            'pressureDevice': pressureName,
        })
        PatchPipette.__init__(self, deviceManager, config, name)

    # def getTPRange(self):
    #     return self.mies.getTPRange()

    # def setState(self, state):
    #     if state == 'seal':
    #         self.mies.selectHeadstage(self._headstage)
    #         self.mies.setSeal(self._headstage)
    #     elif state == 'bath':
    #         self.mies.selectHeadstage(self._headstage)
    #         self.mies.setApproach(self._headstage)
    #     self.state = state
    #     self.sigStateChanged.emit(self)

    def setActive(self, active):
        # raise Exception("stack trace")
        self.mies.setHeadstageActive(self._headstage, active)
        PatchPipette.setActive(self, active)

    def setSelected(self):
        self.mies.selectHeadstage(self._headstage)

    def quit(self):
        self.mies.quit()
        super(MIESPatchPipette, self).quit()
