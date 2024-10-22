from __future__ import print_function
from collections import OrderedDict
from acq4.devices.PatchPipette.states import PatchPipetteState
import acq4.devices.PatchPipette.states as states
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager


class BathStateMIES(PatchPipetteState):
    stateName = 'bath'

    def initialize(self):
        PatchPipetteState.initialize(self)
        self.dev.mies.selectHeadstage(self.dev._headstage)
        self.dev.mies.setApproach(self.dev._headstage)


class SealStateMIES(PatchPipetteState):
    stateName = 'seal'

    def initialize(self):
        PatchPipetteState.initialize(self)
        self.dev.mies.selectHeadstage(self.dev._headstage)
        self.dev.mies.setSeal(self.dev._headstage)


class MIESPatchPipetteStateManager(PatchPipetteStateManager):
    stateHandlers = PatchPipetteStateManager.stateHandlers.copy()
    stateHandlers['seal'] = SealStateMIES
    stateHandlers['bath'] = BathStateMIES
    # stateHandlers = OrderedDict([
    #     # ('out', states.PatchPipetteOutState),
    #     # ('bath', MIESPatchPipetteBathState),
    #     # ('approach', states.PatchPipetteApproachState),
    #     # ('cell detect', states.PatchPipetteCellDetectState),
        # ('seal', MIESPatchPipetteSealState),
    #     # ('cell attached', states.PatchPipetteCellAttachedState),
    #     # ('break in', states.PatchPipetteBreakInState),
    #     # ('whole cell', states.PatchPipetteWholeCellState),
    #     # ('reseal', states.PatchPipetteResealState),
    #     # ('blowout', states.PatchPipetteBlowoutState),
    #     # ('broken', states.PatchPipetteBrokenState),
    #     # ('fouled', states.PatchPipetteFouledState),
    #     # ('clean', states.PatchPipetteCleanState),
    # ])
