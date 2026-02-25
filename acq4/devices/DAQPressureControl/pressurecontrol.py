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
        - At least one source must be 'regulator', which will also require a 'pressureControl'
          channel declared.

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

    # 3-state controller:
    PressureController:
        driver: 'DAQPressureControl'
        daqDevice: 'PressureChannels'
        sources:
            regulator:
                pressureControl: 'pressure_out'
                valve_1: 1  # activate only valve 1 for regulator
                valve_2: 0
            atmosphere:
                valve_1: 0  # deactivate all valves for atmosphere
                valve_2: 0
            user:
                valve_1: 0  # activate only valve 2 for user
                valve_2: 1

    # Regulator-only controller (disabled 'user', simulated 'atmosphere' by setting regulator output to 0):
    PressureController:
        driver: 'DAQPressureControl'
        daqDevice: 'PressureChannels'
        sources:
            regulator:
                pressureControl: 'pressure_out'

    """

    def __init__(self, manager, config, name):
        PressureControl.__init__(self, manager, config, name)

        daqDev = config.pop('daqDevice')
        self.device = manager.getDevice(daqDev)
        self.sources = config.pop('sources')
        if "regulator" not in self.sources:
            raise ValueError(
                'At least one source must be "regulator" with a pressure control channel defined'
            )
        if "pressureControl" not in self.sources['regulator']:
            raise ValueError('Regulator source must define a "pressureControl" channel')
        self._regulatorAtmosphere = 'atmosphere' not in self.sources
        self._simAtmosphereState = {'active': False, 'supplanted pressure': None}
        self.source = self.getSource()

    def _setPressure(self, p):
        self._simAtmosphereState['supplanted pressure'] = p
        if self._regulatorAtmosphere and self._simAtmosphereState['active']:
            p = 0
        self.device.setChanHolding(self._pressureControlChannel(), p)

    def _pressureControlChannel(self) -> str:
        return self.sources['regulator']['pressureControl']

    def getPressure(self):
        if self._regulatorAtmosphere and self._simAtmosphereState['active']:
            return self._simAtmosphereState['supplanted pressure']
        return self.device.getChanHolding(self._pressureControlChannel())

    def getSource(self):
        if self._regulatorAtmosphere and self._simAtmosphereState['active']:
            return 'atmosphere'
        # try to infer current source from channel state
        for source, chans in self.sources.items():
            match = True
            for chan, val in chans.items():
                if chan == 'pressureControl':
                    continue
                if self.device.getChanHolding(chan) != val:
                    match = False
                    break
            if match:
                return source
        return None

    def _setSource(self, source):
        if self._regulatorAtmosphere:
            if source == 'atmosphere':
                self._simAtmosphereState['supplanted pressure'] = self.getPressure()
                self._simAtmosphereState['active'] = True
                self.device.setChanHolding(self._pressureControlChannel(), 0)
                return
            else:
                self._simAtmosphereState['active'] = False
                expected = self._simAtmosphereState['supplanted pressure']
                if expected is not None:
                    self.device.setChanHolding(self._pressureControlChannel(), expected)
        for chan, val in self.sources[source].items():
            if chan == 'pressureControl':
                continue
            self.device.setChanHolding(chan, val)
