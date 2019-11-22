from __future__ import print_function
from collections import OrderedDict
from acq4.devices.PatchPipette.states import PatchPipetteState
import acq4.devices.PatchPipette.states as states
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager


class MIESPatchPipetteBathState(PatchPipetteState):
    stateName = 'bath'

    def initialize(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.setApproach(self._headstage)


class MIESPatchPipetteSealState(PatchPipetteState):
    stateName = 'seal'

    def initialize(self):
        self.dev.mies.selectHeadstage(self._headstage)
        self.dev.mies.setSeal(self._headstage)


class MIESPatchPipetteStateManager(PatchPipetteStateManager):
    stateHandlers = OrderedDict([
        ('out', states.PatchPipetteOutState),
        ('bath', MIESPatchPipetteBathState),
        ('approach', states.PatchPipetteApproachState),
        # ('cell detect', states.PatchPipetteCellDetectState),
        ('seal', MIESPatchPipetteSealState),
        # ('cell attached', states.PatchPipetteCellAttachedState),
        # ('break in', states.PatchPipetteBreakInState),
        # ('whole cell', states.PatchPipetteWholeCellState),
        # ('reseal', states.PatchPipetteResealState),
        # ('blowout', states.PatchPipetteBlowoutState),
        # ('broken', states.PatchPipetteBrokenState),
        # ('fouled', states.PatchPipetteFouledState),
        # ('clean', states.PatchPipetteCleanState),
    ])

