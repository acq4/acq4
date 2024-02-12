import time
from typing import Optional

from acq4.util import Qt, ptime
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
    def rampPressure(
        self,
        target: Optional[float] = None,
        target_tolerance: float = 10,
        maximum: Optional[float] = None,
        minimum: Optional[float] = None,
        rate: Optional[float] = None,
        duration: Optional[float] = None,
        _future: Optional[Future] = None,
    ) -> None:
        if target is None and maximum is None and minimum is None:
            raise ValueError("Must specify at least one of target, maximum, or minimum")
        if target is not None and (maximum is not None or minimum is not None):
            raise ValueError("Cannot specify both target and maximum/minimum")
        if rate is not None and duration is not None:
            raise ValueError("Cannot specify both rate and duration")

        if target is not None:
            minimum = target - target_tolerance
            maximum = target + target_tolerance

        start_pressure = end_pressure = self.getPressure()
        if minimum is not None:
            end_pressure = max(minimum, end_pressure)
        if maximum is not None:
            end_pressure = min(maximum, end_pressure)
        if duration is None:
            if rate is None:
                duration = self.regulatorSettlingTime
            else:
                duration = abs(end_pressure - start_pressure) / rate

        start_time = ptime.time()
        frac_done = 0
        while frac_done < 1:
            frac_done = min((ptime.time() - start_time) / duration, 1)
            self.setPressure("regulator", start_pressure + frac_done * (end_pressure - start_pressure))
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
