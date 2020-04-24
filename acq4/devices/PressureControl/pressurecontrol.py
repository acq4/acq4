from __future__ import print_function
import time
from acq4.util import Qt
from ..Device import Device


class PressureControl(Device):
    """A device for controlling pressure to a single port.

    Pressure control may be implemented by a combination of a pressure regulator
    and multiple valves.
    """
    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure

    def __init__(self, manager, config, name):
        Device.__init__(self, manager, config, name)
        self.source = None
        self.pressure = None
        self.sources = config.get('sources', ())
        self.regulatorSettlingTime = config.get('regulatorSettlingTime', 0.3)

    def setPressure(self, source=None, pressure=None):
        """Set the output pressure (float; in Pa) and/or pressure source (str).
        """
        if source is not None and source not in self.sources:
            raise ValueError('Pressure source "%s" is not valid; available sources are: %s' % (source, self.sources))

        # order of operations depends on the requested source
        if source is not None and source != 'regulator':
            self._setSource(source)
        if pressure is not None:
            self._setPressure(pressure)
        if source == 'regulator':
            if pressure is not None:
                time.sleep(self.regulatorSettlingTime) # let pressure settle before switching valves
            self._setSource(source)

        self.sigPressureChanged.emit(self, self.source, self.pressure)

    def _setPressure(self, p):
        """Set the regulated output pressure (in Pascals).

        Note: this does _not_ change the configuration of any valves.
        """
        self.pressure = p

    def _setSource(self, source):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        self.source = source
