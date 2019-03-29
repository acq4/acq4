from __future__ import print_function
from acq4.util import Qt
from acq4.drivers.sensapex import SensapexDevice, UMP, UMPError
from ..PressureControl import PressureControl


class SensapexPressureControl(PressureControl):
    """Pressure control device driven by Sensapex analog/digital channels.
    """

    def __init__(self, manager, config, name):
        self.devid = config.get('deviceId')       
        address = config.pop('address', None)
        group = config.pop('group', None)
        all_devs = UMP.get_ump(address=address, group=group).list_devices()
        if self.devid not in all_devs:
            raise Exception("Invalid sensapex device ID %s. Options are: %r" % (self.devid, all_devs))

        self.dev = SensapexDevice(self.devid)

        PressureControl.__init__(self, manager, config, name)

        self.pressureChannel = config.pop('pressureChannel')
        self.pressureScale = config.pop('pressureScale')
        self.voltageOffset = config.pop('voltageOffset')
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
        self.pressure = (self.device.get_pressure(self.pressureChannel) - self.voltageOffset) / self.pressureScale

    def _setPressure(self, p):
        """Set the regulated output pressure (in Pascals) to the pipette.

        Note: this does _not_ change the configuration of any values.
        """
        self.device.set_pressure(self.pressure_channel, p * self.pressureScale + self.voltageOffset)
        self.pressure = p

    def _setSource(self, source):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        for chan, val in self.sources[source].items():
            self.device.set_valve(int(chan), val)
        self.source = source