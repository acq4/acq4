from __future__ import print_function
from acq4.util.mies import MIES
from ..PatchClamp import PatchClamp


class MIESPatchClamp(PatchClamp):
    """PatchClamp device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge(True)
        PatchClamp.__init__(self, manager, config, name)

    def autoPipetteOffset(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.autoPipetteOffset()

    def setMode(self, mode):
        print("STUB: set clamp mode %r" % mode)

    def getMode(self):
        return 'ic'

    def setHolding(self, mode, value):
        print("STUB: set clamp holding %r %r" % (mode, value))

    def getHolding(self, mode):
        return 0

    def getState(self):
        return {'mode': 'ic'}
