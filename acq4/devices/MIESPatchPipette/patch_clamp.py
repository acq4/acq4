from acq4.util.mies import MIES
from ..PatchClamp import PatchClamp


class MIESPatchClamp(PatchClamp):
    """PatchClamp device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge()
        PatchClamp.__init__(self, manager, config, name)

    def autoPipetteOffset(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.autoPipetteOffset()

    def setMode(self, mode):
        print(f"STUB: set clamp mode {mode!r}")

    def getMode(self):
        return 'ic'

    def setHolding(self, mode=None, value=None):
        print(f"STUB: set clamp holding {mode!r} {value!r}")

    def getHolding(self, mode=None):
        return 0

    def getState(self):
        return {'mode': 'ic'}
    
    def getDAQName(self, channel):
        return None
    
    def getParam(self, param):
        return None
    
    def deviceInterface(self, win):
        return None
