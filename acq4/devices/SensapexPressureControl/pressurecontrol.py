from __future__ import print_function

from acq4.drivers.sensapex import SensapexDevice, UMP
from ..PressureControl import PressureControl


class SensapexPressureControl(PressureControl):
    """Pressure control device driven by Sensapex analog/digital channels.
    """

    def __init__(self, manager, config, name):
        self.devid = config.get('deviceId')       
        address = config.pop('address', None)
        group = config.pop('group', None)
        ump = UMP.get_ump(address=address, group=group)
        self.dev = ump.get_device(self.devid)

        PressureControl.__init__(self, manager, config, name)

        self.pressureChannel = config.pop('pressureChannel')
        self.sources = config.pop('sources')

        # try to infer current source from channel state
        for source, chans in self.sources.items():
            match = True
            for chan, val in chans.items():
                if self.dev.get_valve(int(chan)) != val:
                    match = False
                    break
            if match:
                self.source = source
                break
        self.pressure = self.dev.get_pressure(self.pressureChannel) * 1000

    def _setPressure(self, p):
        """Set the regulated output pressure (in Pascals) to the pipette.

        Note: this does _not_ change the configuration of any values.
        """
        self.dev.set_pressure(self.pressureChannel, p / 1000.)
        self.pressure = p

    def _setSource(self, source):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        for chan, val in self.sources[source].items():
            self.dev.set_valve(int(chan), val)
        self.source = source
