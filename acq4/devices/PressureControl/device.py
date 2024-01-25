import time

from acq4.util import Qt
from .widgets import PressureControlWidget
from ..Device import Device
from ...util.future import Future


class PressureControl(Device):
    """A device for controlling pressure to a single port.

    Pressure control may be implemented by a combination of a pressure regulator
    and multiple valves.

    The configuration for these devices should look like::

        maximum: 50*kPa
        minimum: -50*kPa
        regulatorSettlingTime: 0.3
    """
    sigBusyChanged = Qt.Signal(object, object)  # self, busyOrNot
    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure

    def __init__(self, manager, config, name):
        Device.__init__(self, manager, config, name)
        self.maximum = config.get('maximum', 5e4)
        self.minimum = config.get('minimum', -5e4)
        self.pressure = None
        self.regulatorSettlingTime = config.get('regulatorSettlingTime', 0.3)
        self.source = None
        self.sources = ("regulator", "user", "atmosphere")

    @Future.wrap
    def attainPressure(self, source, maximum=None, minimum=None, _future=None):
        self.setPressure(source)
        while True:
            pressure = self.getPressure()
            if minimum is not None and pressure < minimum:
                self.setPressure(source, pressure=minimum)
            elif maximum is not None and pressure > maximum:
                self.setPressure(source, pressure=maximum)
            else:
                break
            _future.sleep(self.regulatorSettlingTime)

    def setPressure(self, source=None, pressure=None):
        """Set the output pressure (float; in Pa) and/or pressure source (str).
        """
        if source is not None and source not in self.sources:
            raise ValueError(f'Pressure source "{source}" is not valid; available sources are: {self.sources}')

        # order of operations depends on the requested source
        if source is not None and source != 'regulator':
            self._setSource(source)
            self.source = source
        if pressure is not None:
            self._setPressure(pressure)
            self.pressure = pressure
        if source == 'regulator':
            if pressure is not None:
                time.sleep(self.regulatorSettlingTime)  # let pressure settle before switching valves
            self._setSource(source)
            self.source = source

        self.sigPressureChanged.emit(self, self.source, self.pressure)

    def _setPressure(self, p):
        """Set the regulated output pressure (in Pascals).
        """
        raise NotImplementedError()

    def getPressure(self):
        raise NotImplementedError()

    def setSource(self, source):
        self.setPressure(source=source)

    def _setSource(self, source):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        raise NotImplementedError()

    def getSource(self):
        raise NotImplementedError()

    def getBusyStatus(self):
        """Override this and emit sigBusyChanged appropriately if your subclass implements a busy state."""
        return False

    def deviceInterface(self, win):
        return PressureControlWidget(dev=self)
