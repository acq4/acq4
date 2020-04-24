from __future__ import print_function, absolute_import
from acq4.util import Qt
from ..PressureControl import PressureControl


class DAQPressureControl(PressureControl):
    """Pressure control device driven by DAQ analog/digital channels.
    """

    def __init__(self, manager, config, name):
        PressureControl.__init__(self, manager, config, name)

        daqDev = config.pop('daqDevice')
        self.device = manager.getDevice(daqDev)
        self.sources = config.pop('sources')

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
