from __future__ import print_function

from ..PressureControl import PressureControl


class DAQPressureControl(PressureControl):
    """
    Pressure control device using DAQ analog/digital channels.
    
    Controls pressure using a combination of analog output for regulator pressure
    and digital outputs for valve switching between pressure sources.
    
    Configuration options:
    
    * **daqDevice** (str, required): Name of DAQGeneric device controlling valves and regulator
    
    * **sources** (dict, required): Valve configurations for each pressure source
        - Key: Source name ('regulator', 'atmosphere', 'user')
        - Value: Dict mapping valve channel names to states (0/1)
    
    Standard PressureControl configuration options (see PressureControl base class):
    
    * **maximum** (float, optional): Maximum pressure limit in Pa
    
    * **minimum** (float, optional): Minimum pressure limit in Pa
    
    * **regulatorSettlingTime** (float, optional): Time for pressure to settle
    
    The configuration for these devices might look like::

    PressureChannels:
        driver: 'DAQGeneric'
        channels:
            valve_1:
                device: 'DAQ'
                channel: '/Dev2/line0'
                type: 'do'
            valve_2:
                device: 'DAQ'
                channel: '/Dev2/line1'
                type: 'do'
            pressure_out:
                device: 'DAQ'
                channel: '/Dev2/ao0'
                type: 'ao'

    PressureController:
        driver: 'DAQPressureControl'
        daqDevice: 'PressureChannels'
        sources:
            regulator:
                valve_1: 1  # activate only valve 1 for regulator
                valve_2: 0
            atmosphere:
                valve_1: 0  # deactivate all valves for atmosphere
                valve_2: 0
            user:
                valve_1: 0  # activate only valve 2 for user
                valve_2: 1
    """

    def __init__(self, manager, config, name):
        PressureControl.__init__(self, manager, config, name)

        daqDev = config.pop('daqDevice')
        self.device = manager.getDevice(daqDev)
        self.sources = config.pop('sources')

        self.source = self.getSource()

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
