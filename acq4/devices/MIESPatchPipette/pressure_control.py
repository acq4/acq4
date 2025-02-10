from __future__ import print_function

from acq4.util.mies import MIES
from ..PressureControl import PressureControl

PSI_PASCAL = 6894.76

class MIESPressureControl(PressureControl):
    """PressureControl device implemented over MIES bridge
    """

    def __init__(self, manager, config, name):
        self._headstage = config.pop('headstage')
        self.mies = MIES.getBridge()
        PressureControl.__init__(self, manager, config, name)

    def _setPressure(self, pressure):
        # print("STUB: set pressure", source, pressure)
        self.mies.selectHeadstage(self._headstage)
        self.mies.setManualPressure(pressure / PSI_PASCAL)

    def getPressure(self):
        return self.pressure

    def getSource(self):
        return self.source

    def _setSource(self, source):
        self.mies.selectHeadstage(self._headstage)
        self.mies.setPressureSource(source)
