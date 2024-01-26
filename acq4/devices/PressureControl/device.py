import numpy as np
from typing import Optional

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
    def attainPressure(
        self,
        source: str = "regulator",
        target: Optional[float] = None,
        target_tolerance: float = 10,
        maximum: Optional[float] = None,
        minimum: Optional[float] = None,
        rate: Optional[float] = None,
        _future: Optional[Future] = None,
    ) -> None:
        if target is None and maximum is None and minimum is None:
            raise ValueError("Must specify at least one of target, maximum, or minimum")
        if target is not None and (maximum is not None or minimum is not None):
            raise ValueError("Cannot specify both target and maximum/minimum")
        # TODO do we need to guarantee that the source gets set?

        def value_is_out_of_bounds(val):
            if minimum is not None and val < minimum:
                return True
            if maximum is not None and val > maximum:
                return True
            if target is not None and abs(val - target) > target_tolerance:
                return True
            return False

        start = time.time()
        measured = self.getPressure()
        prevent_overshoot = lambda x: x  # default no-op for "target" mode, which can overshoot
        if minimum is not None and measured < minimum:
            target = minimum
            prevent_overshoot = lambda x: np.clip(x, None, target)
        elif maximum is not None and measured > maximum:
            target = maximum
            prevent_overshoot = lambda x: np.clip(x, target, None)
        elif target is None:
            return  # we're already in range

        while value_is_out_of_bounds(measured):
            dt = time.time() - start
            if rate is None:
                step = target
            else:
                step = prevent_overshoot(measured + abs(rate) * dt * np.sign(target - measured))
            self.setPressure(source=source, pressure=step)
            _future.sleep(self.regulatorSettlingTime)
            measured = self.getPressure()

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
