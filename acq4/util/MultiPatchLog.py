from typing import Any

import json
import numpy as np
from MetaArray import MetaArray


TEST_PULSE_METAARRAY_INFO = [
    {'name': 'event_time', 'type': 'float', 'units': 's'},
    {'name': 'baselinePotential', 'type': 'float', 'units': 'V'},
    {'name': 'baselineCurrent', 'type': 'float', 'units': 'A'},
    {'name': 'peakResistance', 'type': 'float', 'units': 'ohm'},
    {'name': 'steadyStateResistance', 'type': 'float', 'units': 'ohm'},
    {'name': 'fitExpAmp', 'type': 'float'},
    {'name': 'fitExpTau', 'type': 'float'},
    {'name': 'fitExpYOffset', 'type': 'float'},
    {'name': 'fitExpXOffset', 'type': 'float', 'units': 's'},
    {'name': 'capacitance', 'type': 'float', 'units': 'F'},
]


class MultiPatchLog(object):
    def __init__(self, filename=None):
        self._filename = filename
        self._devices = {}
        self._minTime = None
        self._maxTime = None

        if filename is not None:
            self.process(filename)

    def process(self, filename) -> None:
        def possible_uses_for_type(event_type: str) -> list[str]:
            uses = ['event']
            if event_type in {'move_start', 'move_stop'}:
                uses.append('position')
            if event_type in {'pressure_changed'}:
                uses.append('pressure')
            if event_type in {'pipette_transform_changed'}:
                uses.append('pipette_transform')
            if event_type in {'state_change'}:
                uses.append('state_change')
            if event_type in {'auto_bias_enabled', 'auto_bias_target_changed'}:
                uses.append('auto_bias_target')
            if event_type in {'target_changed'}:
                uses.append('target')
            # if event_type in {'move_requested'}:
            #     uses.append('move_request')
            if event_type in {'test_pulse'}:
                uses.append('test_pulse')
            return uses

        with open(filename, 'rb') as fh:
            events: list[dict[str, Any]] = [json.loads(line.rstrip(b',\r\n')) for line in fh]

            events_by_dev_and_use = {}
            bool_fields = ('clean', 'broken', 'active', 'enabled')
            for ev in events:
                is_true = [ev[f] for f in bool_fields if f in ev]
                ev["is_true"] = not is_true or any(is_true)  # empty should mean True
                for use in possible_uses_for_type(ev['event']):
                    events_by_dev_and_use.setdefault(ev['device'], {}).setdefault(use, [])
                    events_by_dev_and_use[ev['device']][use].append(ev)
            for dev in events_by_dev_and_use:
                self._devices[dev] = self._initial_data_structures(events_by_dev_and_use[dev])
                for use in events_by_dev_and_use[dev]:
                    for i, event in enumerate(events_by_dev_and_use[dev][use]):
                        self._devices[dev][use][i] = self._prepare_event_for_use(event, use)
                        if use == 'position':
                            time, *pos = self._prepare_event_for_use(event, use)
                            self._devices[dev]['position_ITS'][time] = pos

    def devices(self) -> list[str]:
        return list(self._devices.keys())

    def __getitem__(self, dev: str) -> dict[str, Any]:
        return self._devices[dev]

    def state(self, time):
        # Used by MultiPatchLogCanvasItem
        return {
            dev: {'position': self._devices[dev]['position_ITS'][time]}
            for dev in self.devices()
        }

    def firstTime(self):
        return self._minTime

    def lastTime(self):
        return self._maxTime

    @staticmethod
    def _initial_data_structures(events_by_use: dict[str, list]) -> dict[str, Any]:
        def count_for_use(use: str):
            return len(events_by_use[use]) if use in events_by_use else 0

        return {
            # 'position_ITS' is a special case, to support Canvas
            'position_ITS': IrregularTimeSeries(interpolate=True),
            'position': np.zeros(
                (count_for_use('position'), 4),
                dtype=float,
            ),
            'event': np.zeros(
                count_for_use('event'),
                dtype=[('time', float), ('event', 'U32'), ('bool', 'bool')],
            ),
            'pressure': np.zeros(
                count_for_use('pressure'),
                dtype=[('time', float), ('pressure', float), ('source', 'U32')],
            ),
            'pipette_transform': np.zeros(
                (count_for_use('pipette_transform'), 4),
                dtype=float,
            ),
            'state_change': np.zeros(
                count_for_use('state_change'),
                dtype=[('time', float), ('state', 'U32'), ('old_state', 'U32')],
            ),
            'auto_bias_target': np.zeros(
                (count_for_use('auto_bias_target'), 2),
                dtype=float,
            ),
            'target': np.zeros(
                (count_for_use('target'), 4),
                dtype=float,
            ),
            # TODO how do I want to structure move_request?
            # 'move_request': np.zeros(
            #     count_for_use('move_request'),
            #     dtype=[('time', float), ('path', 'U32')],
            # ),
            'test_pulse': np.zeros(
                (count_for_use('test_pulse'), len(TEST_PULSE_METAARRAY_INFO)),
                dtype=float,
            ),
            # 'test_pulse': MetaArray(
            #     np.zeros(
            #         (count_for_use('test_pulse'), len(TEST_PULSE_METAARRAY_INFO)),
            #         dtype=float),
            #     info=TEST_PULSE_METAARRAY_INFO),
        }

    @staticmethod
    def _prepare_event_for_use(event: dict, use: str) -> tuple[float, ...]:
        if use == 'event':
            return event['event_time'], event['event'], event['is_true']
        if use == 'position':
            return event['event_time'], *event['position']
        if use == 'pressure':
            return event['event_time'], event['pressure'], event['source']
        if use == 'pipette_transform':
            return event['event_time'], *event['globalPosition']
        if use == 'state_change':
            return event['event_time'], event['state'], event['old_state']
        if use == 'auto_bias_target':
            return event['event_time'], event['target'] if event.get('enabled', True) else np.nan
        if use == 'target':
            return event['event_time'], *event['target_position']
        # if use == 'move_request':
        #     return event['event_time'], event['opts']
        if use == 'test_pulse':
            return tuple(event[info['name']] for info in TEST_PULSE_METAARRAY_INFO)


class IrregularTimeSeries(object):
    """An irregularly-sampled time series.
    
    Allows efficient retrieval of the series value at any time using a lookup table.
    Intended for cases where the lookup table would be reasonably-sized (for example,
    an hour of events indexed at 1-second resolution). For larger data sets, a 
    b-tree would be a more reasonable approach.
    
    If enabled, values are interpolated linearly. Values may be of any type,
    but only scalar, array, and tuple-of-scalar types may be interpolated.

    Example::

        # Initialize with a list of (time, value) pairs
        series = IrregularTimeSeries(data=[
            (10.5, 0.1),
            (12.0, 0.7),
            (16.0, 0.5),
            (34.2, 1.2),
        ], interpolate=True)

        # Look up the series value at any arbitrary time
        series[5.0]   # returns None because the series begins at 10.0
        series[14.0]  # returns 0.6; interpolated between 2nd and 3rd timepoints
        series[50]    # returns 1.2; the last value in the time series
    """
    def __init__(self, data=None, interpolate=False, resolution=1.0):
        self.interpolate = interpolate
        self._resolution = resolution

        self.events = []
        # each value maps a time in seconds to the index of the value recorded immediately after the time
        self.index = []
        self._startTime = None

        if data is not None:
            self.extend(data)

    def __setitem__(self, time, value):
        """Set the value of this series at a specific time.

        Points in the series must be added in increasing chronological order.
        It is allowed to add multiple values for the same time point.
        """
        if len(self.events) > 0 and time < self.events[-1][0]:
            raise ValueError("Time points must be added in increasing order.")

        if self._startTime is None:
            self._startTime = time
        i = self._getIndex(time)

        # Extend index
        dif = i + 1 - len(self.index)
        if dif > 0:
            self.index.extend([len(self.events)] * dif)
        self.index[i] = len(self.events)

        self.events.append((float(time), value))

    def extend(self, data):
        for t, v in data:
            self[t] = v

    def __getitem__(self, time):
        """Return the value of this series at the given time.
        """
        events = self.events
        if len(events) == 0:
            return None
        if time <= self._startTime:
            return None
        if time >= events[-1][0]:
            return events[-1][1]

        # Use index to find a nearby event
        i = self.index[min(self._getIndex(time), len(self.index)-1)]

        if events[i][0] > time:
            # walk backward to the requested event
            while self.events[i][0] > time:
                i -= 1
        elif events[i][0] < time:
            # walk forward to the requested event
            while i+1 < len(self.events) and self.events[i+1][0] <= time:
                i += 1
        else:
            return events[i][1]

        # interpolate if requested
        if not self.interpolate:
            return events[i][1]
        t1, v1 = events[i]
        t2, v2 = events[i+1]
        return self._interpolate(time, v1, v2, t1, t2)

    def _getIndex(self, t):
        return int((t - self._startTime) / self._resolution)

    @staticmethod
    def _interpolate(t, v1, v2, t1, t2):
        s = (t - t1) / (t2 - t1)
        assert 0.0 <= s <= 1.0
        if isinstance(v1, (tuple, list)):
            return tuple(v1[k] * (1.0 - s) + v2[k] * s for k in range(len(v1)))
        else:
            return v1 * (1.0 - s) + v2 * s

    def times(self):
        """Return a list of the time points in the series.
        """
        return [ev[0] for ev in self.events]

    def values(self):
        """Return a list of the values at each point in the series.
        """
        return [ev[1] for ev in self.events]

    def firstValue(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[0][1]

    def lastValue(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[-1][1]

    def firstTime(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[0][0]

    def lastTime(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[-1][0]

    def __len__(self):
        return len(self.events)
