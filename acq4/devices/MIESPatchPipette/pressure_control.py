from __future__ import print_function

from acq4.util.mies import MIES
from ..PressureControl import PressureControl


class MIESPressureControl(PressureControl):
    """PressureControl device implemented over MIES bridge
    """

    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge(True)
        PressureControl.__init__(self, manager, config, name)

    def _setPressure(self, source=None, pressure=None):
        """Set the output pressure (float; in Pa) and/or pressure source (str).
        """
        print("STUB: set pressure", source, pressure)

    def getPressure(self):
        pass

    def getSource(self):
        pass

    def _setSource(self, source):
        pass
