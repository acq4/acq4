from acq4.util.mies import MIES
from ..PatchClamp import PatchClamp


class MIESPatchClamp(PatchClamp):
    """PatchClamp device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = headstage
        self.mies = MIES.getBridge(True)
        PatchClamp.__init__(self, manager, config, name)

    def autoPipetteOffset(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.autoPipetteOffset()


