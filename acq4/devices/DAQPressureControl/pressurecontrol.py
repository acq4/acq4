from __future__ import print_function

from ..PressureControl import PressureControl


class DAQPressureControl(PressureControl):
    """Pressure control device driven by DAQ analog/digital channels.
    The configuration for these devices should look like:
        sources:
            regulator:
                channel_name: TODO what?
            atmosphere:
                channel_name: TODO what?
            user:
                channel_name: TODO what?
    """

    def __init__(self, manager, config, name):
        PressureControl.__init__(self, manager, config, name)

        daqDev = config.pop('daqDevice')
        self.device = manager.getDevice(daqDev)
        self.sources = config.pop('sources')

        self.source = self.getSource()
        self.pressure = self.getPressure()

    def _setPressure(self, p):
        self.device.setChanHolding('pressure_out', p)

    def getPressure(self):
        return self.device.getChanHolding('pressure_out')

    def getSource(self):
        # try to infer current source from channel state
        for source, chans in self.sources.items():
            match = True
            for chan, val in chans.items():
                if self.device.getChanHolding(chan) != val:
                    match = False
                    break
            if match:
                return source

    def _setSource(self, source):
        for chan, val in self.sources[source].items():
            self.device.setChanHolding(chan, val)
