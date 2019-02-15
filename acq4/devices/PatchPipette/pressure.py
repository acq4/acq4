from __future__ import print_function
from acq4.util import Qt
from ...Manager import getManager


class PressureControl(Qt.QObject):

    sigPressureChanged = Qt.Signal(object, object, object)  # self, source, pressure

    def __init__(self, deviceName):
        Qt.QObject.__init__(self)
        man = getManager()
        self.device = man.getDevice(deviceName)

        self.sources = {
            'atmosphere': {'user_valve': 0, 'regulator_valve': 0},
            'user': {'user_valve': 1, 'regulator_valve': 0},
            'regulator': {'regulator_valve': 1},
        }

        self.source = None
        # try to infer current source from channel state
        for source, chans in self.sources.items():
            match = True
            for chan, val in chans.items():
                if self.device.getChanHolding(chan) != val:
                    match = False
                    break
            if match:
                self.source = source
                break
        self.pressure = self.device.getChanHolding('pressure_out')

    def setPressure(self, source=None, pressure=None):
        """Set the pipette pressure (float; in Pa) and/or pressure source (str).
        """
        if source is not None and source not in self.sources:
            raise ValueError('Pressure source "%s" is not valid; available sources are: %s' % (source, self.sources))

        # order of operations depends on the requested source
        if source is not None and source != 'regulator':
            self._setSource(source)
        if pressure is not None:
            self._setPressure(pressure)
        if source == 'regulator':
            self._setSource(source)

        self.sigPressureChanged.emit(self, self.source, self.pressure)

    def _setPressure(self, p):
        """Set the regulated output pressure (in Pascals) to the pipette.

        Note: this does _not_ change the configuration of any values.
        """
        self.device.setChanHolding('pressure_out', p)
        self.pressure = p

    def _setSource(self, source):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        for chan, val in self.sources[source].items():
            self.device.setChanHolding(chan, val)
        self.source = source
