from __future__ import print_function
import numpy as np
from ..PatchPipette import PatchPipette
from acq4.util.mies import MIES
from .patch_clamp import MIESPatchClamp
from .pressure_control import MIESPressureControl
from .testpulse import MIESTestPulseThread
from .states import MIESPatchPipetteStateManager


class MIESPatchPipette(PatchPipette):
    """A single patch pipette channel that uses a running MIES instance to handle
    electrophysiology and pressure control.
    """
    defaultTestPulseThreadClass = MIESTestPulseThread
    defaultStateManagerClass = MIESPatchPipetteStateManager

    def __init__(self, deviceManager, config, name):
        self.mies = MIES.getBridge(True)
        self._headstage = config.pop('headstage')

        # create pressure and clamp devices
        clampName = name + "_clamp"
        clamp = MIESPatchClamp(
            deviceManager, 
            config={'headstage': self._headstage},
            name=clampName)

        
        pressureName = name + "_pressure"
        pressure = MIESPressureControl(
            deviceManager, 
            config={'headstage': self._headstage},
            name=pressureName)

        config.update({
            'clampDevice': clampName,
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
        self.mies.setHeadstageActive(self._headstage, active)
        PatchPipette.setActive(self, active)

    def setSelected(self):
        self.mies.selectHeadstage(self._headstage)

    def quit(self):
        self.mies.quit()
        super(MIESPatchPipette, self).quit()
