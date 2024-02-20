import json
import numpy as np
from typing import Any

import pyqtgraph as pg
from acq4.filetypes.FileType import FileType
from acq4.util import Qt

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
        i = self.index[min(self._getIndex(time), len(self.index) - 1)]

        if events[i][0] > time:
            # walk backward to the requested event
            while self.events[i][0] > time:
                i -= 1
        elif events[i][0] < time:
            # walk forward to the requested event
            while i + 1 < len(self.events) and self.events[i + 1][0] <= time:
                i += 1
        else:
            return events[i][1]

        # interpolate if requested
        if not self.interpolate:
            return events[i][1]
        t1, v1 = events[i]
        t2, v2 = events[i + 1]
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


class MultiPatchLogData(object):
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
            if event_type in {'state_change', 'state_event'}:
                uses.append('state')
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
                        if self._minTime is None or event['event_time'] < self._minTime:
                            self._minTime = event['event_time']
                        if self._maxTime is None or event['event_time'] > self._maxTime:
                            self._maxTime = event['event_time']
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
            'state': list(range(count_for_use('state'))),
            'auto_bias_target': np.zeros(
                (count_for_use('auto_bias_target'), 2),
                dtype=float,
            ),
            'target': np.zeros(
                (count_for_use('target'), 4),
                dtype=float,
            ),
            # TODO save field of view dimensions to show stage (camera) position
            # TODO save position polling
            # TODO save objective
            # TODO save lighting
            # TODO save clamp mode changes, holding voltage, current
            # TODO save entire test pulse
            # TODO how do I want to structure move_request?
            # 'move_request': np.zeros(
            #     count_for_use('move_request'),
            #     dtype=[('time', float), ('path', 'U32')],
            # ),
            'test_pulse': np.zeros(
                count_for_use('test_pulse'),
                dtype=[(info['name'], info['type']) for info in TEST_PULSE_METAARRAY_INFO],
            ),
            # 'test_pulse': MetaArray(
            #     np.zeros(
            #         (count_for_use('test_pulse'), len(TEST_PULSE_METAARRAY_INFO)),
            #         dtype=float),
            #     info=TEST_PULSE_METAARRAY_INFO),
        }

    @staticmethod
    def _prepare_event_for_use(event: dict, use: str) -> tuple[Any, ...]:
        event_time = float(event['event_time'])
        if use == 'event':
            return event_time, event['event'], event['is_true']
        if use == 'position':
            return event_time, *event['position']
        if use == 'pressure':
            return event_time, event['pressure'], event['source']
        if use == 'pipette_transform':
            return event_time, *event['globalPosition']
        if use == 'state':
            return event_time, event['state'], event.get('info', '')
        if use == 'auto_bias_target':
            return event_time, event['target'] if event.get('enabled', True) else np.nan
        if use == 'target':
            return event_time, *event['target_position']
        # if use == 'move_request':
        #     return event_time, event['opts']
        if use == 'test_pulse':
            return tuple(event[info['name']] for info in TEST_PULSE_METAARRAY_INFO)


class MultiPatchLog(FileType):
    """File type written by MultiPatch module.
    """
    extensions = ['.log']   # list of extensions handled by this class
    dataTypes = []    # list of python types handled by this class
    priority = 0      # priority for this class when multiple classes support the same file types
    
    @classmethod
    def read(cls, fileHandle) -> MultiPatchLogData:
        """Read a file, return a data object"""
        return MultiPatchLogData(fileHandle.name())
        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise, return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return cls.priority
        return False


class PipettePathWidget(object):
    def __init__(self, name: str, path: np.ndarray, plot: pg.PlotItem, states: list[tuple[float, str, str]], start_time: float):
        self._name = name
        path[:, 0] -= start_time
        self._path = path
        self._states = [[s[0] - start_time, *s[1:]] for s in states]
        # TODO handle empty states, path
        # TODO time as color. twilight_shifted is maybe a good colormap
        # TODO z as alpha?
        self._plot = pg.PlotDataItem(self._path[:, 1], self._path[:, 2], pen=pg.mkPen('b', width=2))
        plot.addItem(self._plot)
        self._arrow = pg.ArrowItem(pen=pg.mkPen('b', width=2))
        self._arrow.setPos(self._path[0, 1], self._path[0, 2])
        plot.addItem(self._arrow)
        self._label = pg.TextItem(text=f"{name}: {states[0][1]}\n {states[0][2]}", color=pg.mkColor('w'))
        self._label.setPos(self._path[0, 1], self._path[0, 2])
        plot.addItem(self._label)

    def getPlot(self) -> pg.PlotDataItem:
        return self._plot

    def setTime(self, time: float):
        next_index = min(np.searchsorted(self._path[:, 0], time), len(self._path) - 1)
        if next_index == 0:
            pos = self._path[0, 1:]
        elif next_index == len(self._path) - 1:
            pos = self._path[-1, 1:]
        else:
            part = (time - self._path[next_index - 1, 0]) / (self._path[next_index, 0] - self._path[next_index - 1, 0])
            pos = (1 - part) * self._path[next_index - 1, 1:] + self._path[next_index, 1:] * part
        self._arrow.setPos(pos[0], pos[1])
        self._label.setPos(pos[0], pos[1])

        state = self._states[0]
        for s in self._states:
            if s[0] >= time:
                break
            state = s
        self._label.setText(f"{self._name}: {state[1]}\n{state[2]}")

    def getPosLabel(self) -> pg.ArrowItem:
        return self._arrow

    def setParent(self, parent):
        self._plot.setParent(parent)
        self._label.setParent(parent)

    def deleteLater(self):
        self._plot.deleteLater()
        self._plot = None
        self._arrow = None
        self._label.deleteLater()
        self._label = None


class MultiPatchLogWidget(Qt.QWidget):
    # TODO selectable event types to display?
    # TODO images should be displayed as the timeline matches?
    # TODO option to add plots for anything else
    # TODO add target position
    # TODO we don't poll the position, so the movement requests are all we have
    # TODO investigate what logging autopatch module does
    # TODO associate all images and recordings with the cell
    # TODO multipatch logs are one-per-cell
    # TODO they can reference each other?
    # TODO selectable cells, pipettes
    # TODO filter log messages by type
    # TODO don't try to display position Z
    # TODO scale markers with si units
    # TODO make sure all the time values start at 0
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logFiles = []
        self._pipettes: list[PipettePathWidget] = []
        self._cells = []
        self._events = []
        self._widgets = []
        self._pinned_image_z = -10000
        self._layout = Qt.QVBoxLayout()
        self.setLayout(self._layout)
        self._plots_widget = pg.GraphicsLayoutWidget()
        self._widgets.append(self._plots_widget)
        self._layout.addWidget(self._plots_widget)
        self._visual_field = self._plots_widget.addPlot()
        self._visual_field.setAspectLocked(ratio=1.0001)  # workaround weird bug with qt
        self._resistance_plot = self._plots_widget.addPlot(name='Resistance', labels=dict(bottom='s', left='Ω'), row=1, col=0)
        self._analysis_plot = self._plots_widget.addPlot(name='Analysis', row=2, col=0)
        self._analysis_plot.addItem(pg.InfiniteLine(movable=True, pos=0.9998, angle=0, pen=pg.mkPen('w')))
        self._analysis_plot.setXLink(self._resistance_plot)
        self._timeSlider = pg.InfiniteLine(
            movable=True,
            angle=90,
            pen=pg.mkPen('r'),
            hoverPen=pg.mkPen('w', width=2),
            label='t={value:0.2f}s',
            labelOpts={'position': 0.1, 'color': pg.mkColor('r'), 'movable': True},
        )
        self._timeSlider.sigPositionChanged.connect(self.timeChanged)
        self._resistance_plot.addItem(self._timeSlider)

        self._timeLabel = Qt.QLabel()
        self._layout.addWidget(self._timeLabel)

    def timeChanged(self, slider: pg.InfiniteLine):
        time = slider.getXPos()
        self._timeLabel.setText(f"{time} s")
        for p in self._pipettes:
            p.setTime(time)

    def startTime(self) -> float:
        return min(log.firstTime() for log in self._logFiles) or 0

    def endTime(self) -> float:
        return max(log.lastTime() for log in self._logFiles) or 0

    def addLog(self, log: "FileHandle"):
        log_data = log.read()
        self._logFiles.append(log_data)
        if log.parent():
            self.loadImagesFromDir(log.parent().parent())
        self.loadImagesFromDir(log.parent())
        for dev in log_data.devices():
            path = log_data[dev]['position']
            states = log_data[dev]['state']
            test_pulses = log_data[dev]['test_pulse']
            if len(path) > 0:
                widget = PipettePathWidget(dev, path=path, plot=self._visual_field, states=states, start_time=self.startTime())
                self._pipettes.append(widget)
            self.plotTestPulses(test_pulses, states)

        self._timeSlider.setBounds([0, self.endTime() - self.startTime()])

    def plotTestPulses(self, test_pulses, states):
        from acq4.devices.PatchPipette.states import ResealAnalysis

        # TODO better colors?
        time = test_pulses['event_time'] - self.startTime()
        if len(time) > 0:
            self._resistance_plot.plot(
                time, test_pulses['steadyStateResistance'], pen=pg.mkPen('b'))
            self._resistance_plot.plot(
                time, test_pulses['peakResistance'], pen=pg.mkPen('g'))
            # plot the exponential average as is used by the reseal logic
            analyzer = ResealAnalysis(1.005, 0.9998, 5, 10)
            measurements = np.concatenate(
                (time[:, np.newaxis], test_pulses['steadyStateResistance'][:, np.newaxis]), axis=1)
            if len(measurements) > 0:
                analysis = analyzer.process_measurements(measurements)
                self._analysis_plot.plot(analysis["time"], analysis["detection"], pen=pg.mkPen('b'))
                tearing = analysis["tearing"].astype(float)
                tearing[analysis["tearing"] < 1] = np.nan
                self._analysis_plot.plot(analysis["time"], tearing, pen=pg.mkPen('r'))

            last_time = None
            last_state = None
            region_idx = 0
            for state in states:
                if state[2] == '':  # full state change
                    if last_time is not None:
                        brush = pg.mkBrush(pg.intColor(region_idx, hues=8, alpha=30))
                        region_idx += 1
                        self._addRegion(last_time - self.startTime(), state[0] - self.startTime(), brush, last_state)
                    last_time = state[0]
                    last_state = state[1]
                else:  # status update
                    color = pg.mkColor(255, 255, 255, 80)
                    line = pg.InfiniteLine(movable=False, pos=state[0] - self.startTime(), angle=90,
                                           pen=pg.mkPen(color))
                    self._analysis_plot.addItem(line)
                    line.label = pg.InfLineLabel(
                        line, state[2], position=0.75, rotateAxis=(1, 0), anchor=(1, 1), color=color)
            if last_time is not None:
                brush = pg.mkBrush(pg.intColor(region_idx, hues=8, alpha=30))
                self._addRegion(last_time - self.startTime(), self.endTime() - self.startTime(), brush, last_state)

    def _addRegion(self, start, end, brush, label):
        # cycle colors
        region = pg.LinearRegionItem([start, end], movable=False, brush=brush)
        self._resistance_plot.addItem(region)
        # TODO connect double-click to zoom to region
        pg.InfLineLabel(region.lines[0], label, position=0.5, rotateAxis=(1, 0), anchor=(1, 1))

    def loadImagesFromDir(self, directory: "DirHandle"):
        # TODO images associated with the correct slice and cell only
        # TODO integrate with time-slider to display and set the qt Z values
        from acq4.util.imaging import Frame

        for f in directory.ls():
            if f.endswith('.tif'):
                f = directory[f]
                frame = Frame(f.read(), f.info().deepcopy())
                frame.loadLinkedFiles(directory)
                img = frame.imageItem()
                img.setZValue(self._pinned_image_z)
                self._pinned_image_z += 1
                self._visual_field.addItem(img)

    def close(self):
        for w in self._widgets:
            w.setParent(None)
            w.deleteLater()
        self._widgets = []
        for p in self._pipettes:
            p.setParent(None)
            p.deleteLater()
        self._pipettes = []
        return super().close()
