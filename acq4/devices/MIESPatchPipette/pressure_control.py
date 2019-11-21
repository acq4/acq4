from acq4.util.mies import MIES
from ..PressureControl import PressureControl


class MIESPressureControl(PressureControl):
    """PressureControl device implemented over MIES bridge
    """
    def __init__(self, manager, config, name):
        self._headstage = headstage
        self.mies = MIES.getBridge(True)
        PressureControl.__init__(self, manager, config, name)

