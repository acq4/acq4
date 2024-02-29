from __future__ import print_function
from collections import OrderedDict
from acq4.devices.PatchPipette.states import PatchPipetteState
import acq4.devices.PatchPipette.states as states
from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager


class BathStateMIES(PatchPipetteState):
    stateName = 'bath'

    def initialize(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.setApproach(self._headstage)


class SealStateMIES(PatchPipetteState):
    stateName = 'seal'

    def initialize(self):
        self.dev.mies.selectHeadstage(self._headstage)
        self.dev.mies.setSeal(self._headstage)


class MIESPatchPipetteStateManager(PatchPipetteStateManager):
    stateHandlers = OrderedDict([
        ('out', states.OutState),
        ('bath', BathStateMIES),
        ('approach', states.ApproachState),
        # ('cell detect', states.CellDetectState),
        ('seal', SealStateMIES),
        # ('cell attached', states.CellAttachedState),
        # ('break in', states.BreakInState),
        # ('whole cell', states.WholeCellState),
        # ('reseal', states.ResealState),
        # ('blowout', states.BlowoutState),
        # ('broken', states.BrokenState),
        # ('fouled', states.FouledState),
        # ('clean', states.CleanState),
    ])

