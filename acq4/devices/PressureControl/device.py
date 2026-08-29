import time
from typing import Optional

from acq4.util import Qt, ptime
from .widgets import PressureControlWidget
from ..Device import Device
from ...util.task import asynch, sleep


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
        manager.globalHalt.add_abort_callback(self.abort, name=f"{name}.abort")

    def abort(self):
        """Vent to atmosphere; the Panic Lock abort callback for pressure control.

        Registered in __init__ (see "Panic Lock Spec.md" §5.2). Venting is the safe
        direction for a pressure device -- it strictly reduces stored energy -- and
        §6.1 lists ``setPressure(source='atmosphere', pressure=0)`` as Allowed while
        HALTED, so this callback cannot trip its own guard (§6.3).
        """
        self.setPressure(source='atmosphere', pressure=0)

    def quit(self):
        self.dm.globalHalt.remove_abort_callback(self.abort)
        Device.quit(self)

    @asynch
    def rampPressure(
        self,
        target: Optional[float] = None,
        target_tolerance: float = 10,
        maximum: Optional[float] = None,
        minimum: Optional[float] = None,
        rate: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> None:
        if target is None and maximum is None and minimum is None:
            raise ValueError("Must specify at least one of target, maximum, or minimum")
        if target is not None and (maximum is not None or minimum is not None):
            raise ValueError("Cannot specify both target and maximum/minimum")
        if rate is not None and duration is not None:
            raise ValueError("Cannot specify both rate and duration")

        # §6.1 lists rampPressure() as Raise. Every step of the ramp goes through
        # setPressure('regulator', ...) and would be refused there anyway; checking
        # up front means the ramp never reads the device or starts its clock.
        self.dm.globalHalt.check()

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
                duration = abs(end_pressure - start_pressure) / abs(rate)

        start_time = ptime.time()
        frac_done = 0
        while frac_done < 1:
            frac_done = min((ptime.time() - start_time) / duration, 1)
            self.setPressure("regulator", start_pressure + frac_done * (end_pressure - start_pressure))
            sleep(self.regulatorSettlingTime)

    def isValidForPatchPipettes(self):
        # only allow use with patch pipettes if regulator control is available (for fine pressure control)
        return 'regulator' in self.sources and 'atmosphere' in self.sources

    def setPressure(self, source=None, pressure=None):
        """Set the output pressure (float; in Pa) and/or pressure source (str).
        """
        if source is not None and source not in self.sources:
            raise ValueError(f'Pressure source "{source}" is not valid; available sources are: {self.sources}')

        # Panic Lock guard ("Panic Lock Spec.md" §6.1/§6.2). This is the funnel for
        # setSource() and rampPressure(), and the guard is *directional*: venting is
        # how a pressure device is made safe, so the abort callback and every state
        # _cleanup() handler must keep working while HALTED (§6.3).
        if not self._isSafeWhileHalted(source, pressure):
            self.dm.globalHalt.check()

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

    def _isSafeWhileHalted(self, source, pressure):
        """Would setPressure(*source*, *pressure*) strictly reduce risk? (§6.1)

        Two conditions, both required:

        * The port ends up on atmosphere. *source* of None means "leave the source
          alone", so the source that decides this is the one that will be active
          after the call -- the requested one if given, else the one active now.
          That is the "setPressure(pressure=...) with non-atmosphere source active"
          row: a bare pressure write is only safe while already vented.
        * No positive or negative pressure is commanded. `pressure=None` (don't
          touch it) and `pressure=0` (wind the regulator down) both qualify; §6.1
          spells out "with or without pressure=0".

        Charging the regulator to a non-zero setpoint is refused even with
        atmosphere selected. §6.1's governing rule is that an operation is
        permitted while HALTED *if and only if it strictly reduces risk*, and
        storing pressure behind a valve does not -- the next valve change would
        deliver it.
        """
        effectiveSource = self.source if source is None else source
        if effectiveSource != 'atmosphere':
            return False
        if pressure is None:
            return True
        try:
            return float(pressure) == 0.0
        except (TypeError, ValueError):
            return False

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
