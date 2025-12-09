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

    # def _setPressure(self, pressure):
    #     self.mies.selectHeadstage(self._headstage)
    #     self.mies.setManualPressure(pressure / PSI_PASCAL)

    def getPressure(self):
        # return self.mies.getManualPressure(self._headstage) * PSI_PASCAL
        return self.mies.getPressureAndSource(self._headstage)[1] * PSI_PASCAL

    def getSource(self):
        # TODO: get source from MIES when this becomes possible
        return self.mies.getPressureAndSource(self._headstage)[0]
    # def _setSource(self, source):
    #     self.mies.selectHeadstage(self._headstage)
    #     self.mies.setPressureSource(self._headstage, source, (self.getPressure() or 0) / PSI_PASCAL)

    def setPressure(self, source=None, pressure=None):
        """Set the output pressure (float; in Pa) and/or pressure source (str).
        """
        # source = source if source is not None else self.getSource()
        # pressure = pressure if pressure is not None else self.getPressure()

        if source is not None and source not in self.sources:
            raise ValueError(f'Pressure source "{source}" is not valid; available sources are: {self.sources}')
        if pressure is not None:
            pressure = pressure / PSI_PASCAL

        # self.mies.setPressureAndSource(self._headstage, source, pressure / PSI_PASCAL).result(timeout=2)
        # self.source = source
        # self.pressure = pressure
        source, pressure = self.mies.setPressureAndSource(self._headstage, source, pressure).result(timeout=2)
        self.source = source
        self.pressure = pressure * PSI_PASCAL

        self.sigPressureChanged.emit(self, self.source, self.pressure)

