from acq4.util.mies import MIES
from ..PressureControl import PressureControl

PSI_PASCAL = 6894.76


class MIESPressureControl(PressureControl):
    """PressureControl device implemented over MIES bridge"""

    def __init__(self, manager, config, name):
        self._headstage = config.pop("headstage")
        self.mies = MIES.getBridge()
        PressureControl.__init__(self, manager, config, name)
        self.source = 'atmosphere'

    def getPressure(self):
        return self.mies.getPressureAndSource(self._headstage)[1] * PSI_PASCAL

    def getSource(self):
        return self.mies.getPressureAndSource(self._headstage)[0]

    def _applyPressure(self, source, pressure):
        """Set source and pressure in the single bridge call MIES provides.

        Overriding _applyPressure() rather than setPressure() keeps the source
        validation and the Panic Lock guard ("Panic Lock Spec.md" §6.1) in the base
        class, where they cannot be routed around.
        """
        if pressure is not None:
            pressure = pressure / PSI_PASCAL

        source, pressure = self.mies.setPressureAndSource(self._headstage, source, pressure).result(timeout=5)
        self.source = source
        self.pressure = pressure * PSI_PASCAL
