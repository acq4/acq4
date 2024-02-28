import json
import numpy as np
from typing import Any

import pyqtgraph as pg
from acq4.filetypes.FileType import FileType
from acq4.util import Qt
from acq4.util.target import Target

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
            if event_type in {'pipette_transform_changed', 'move_start', 'move_stop'}:
                uses.append('position')
            if event_type in {'pressure_changed'}:
                uses.append('pressure')
            if event_type in {'state_change', 'state_event'}:
                uses.append('state')
            if event_type in {'auto_bias_enabled', 'auto_bias_target_changed'}:
                uses.append('auto_bias_target')
            if event_type in {'target_changed'}:
                uses.append('target')
            # currently ignored:
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
            # TODO save objective
            # TODO save lighting
            # TODO save clamp mode changes, holding voltage, current
            # TODO save entire test pulse
            # 'move_request': is currently ignored
            'test_pulse': np.zeros(
                count_for_use('test_pulse'),
                dtype=[(info['name'], info['type']) for info in TEST_PULSE_METAARRAY_INFO],
            ),
        }

    @staticmethod
    def _prepare_event_for_use(event: dict, use: str) -> tuple[Any, ...]:
        event_time = float(event['event_time'])
        if use == 'event':
            return event_time, event['event'], event['is_true']
        if use == 'position':
            return event_time, *event.get('position', event.get('globalPosition', (np.nan, np.nan, np.nan)))
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
    def __init__(
            self,
            name: str,
            plot: pg.PlotItem,
            log_data: MultiPatchLogData,
            start_time: float,
    ):
        self._name = name
        self._parentPlot = plot
        path = log_data[name]['position'][:]
        path[:, 0] -= start_time
        self._path = path
        states = log_data[name]['state']
        self._states = [[s[0] - start_time, *s[1:]] for s in states]
        self._targets = log_data[name]['target'][:]
        self._targets[:, 0] -= start_time
        self._target = None
        self._targetIndex = None
        self._displayTargetAtTime(0)
        # TODO z as alpha?
        self._futurePlot = pg.PlotDataItem(self._path[:, 1], self._path[:, 2], pen=pg.mkPen((80, 150, 255), width=2))
        self._futurePlot.setZValue(-1)
        plot.addItem(self._futurePlot)
        self._presentPlot = pg.PlotDataItem([], [], pen=pg.mkPen('y', width=2))
        self._presentPlot.setZValue(1)
        plot.addItem(self._presentPlot)
        self._pastPlot = pg.PlotDataItem([], [], pen=pg.mkPen((160, 20, 185), width=2))
        self._pastPlot.setZValue(-2)
        plot.addItem(self._pastPlot)
        self._arrow = pg.ArrowItem(pen=pg.mkPen('w', width=2))
        self._arrow.setPos(self._path[0, 1], self._path[0, 2])
        plot.addItem(self._arrow)
        if len(states) > 0:
            label_text = f"{name}: {states[0][1]}\n {states[0][2]}"
        else:
            label_text = name
        self._label = pg.TextItem(text=label_text, color=pg.mkColor('w'))
        self._label.setPos(self._path[0, 1], self._path[0, 2])
        plot.addItem(self._label)

    def setTime(self, time: float):
        next_index = min(np.searchsorted(self._path[:, 0], time), len(self._path) - 1)
        if next_index == 0:
            pos = self._path[0, 1:]
            self._presentPlot.setData([], [])
        elif next_index == len(self._path) - 1:
            pos = self._path[-1, 1:]
            self._presentPlot.setData([], [])
        else:
            part = (time - self._path[next_index - 1, 0]) / (self._path[next_index, 0] - self._path[next_index - 1, 0])
            pos = (1 - part) * self._path[next_index - 1, 1:] + self._path[next_index, 1:] * part
            self._presentPlot.setData([self._path[next_index - 1, 1], self._path[next_index, 1]],
                                      [self._path[next_index - 1, 2], self._path[next_index, 2]])
        self._pastPlot.setData(self._path[:next_index, 1], self._path[:next_index, 2])
        self._futurePlot.setData(self._path[next_index:, 1], self._path[next_index:, 2])
        self._arrow.setPos(pos[0], pos[1])
        self._label.setPos(pos[0], pos[1])

        state = self._states[0]
        for s in self._states:
            if s[0] >= time:
                break
            state = s
        self._label.setText(f"{self._name}: {state[1]}\n{state[2]}")
        self._displayTargetAtTime(time, pos[2])

    def _displayTargetAtTime(self, time: float, depth: float = 0.0):
        if len(self._targets) == 0:
            return
        index = np.searchsorted(self._targets[:, 0], time) - 1
        if self._targetIndex != index:
            self._targetIndex = index
            if self._target is not None:
                self._parentPlot.removeItem(self._target)
                self._target.setParent(None)
                self._target.deleteLater()
                self._target = None
            if index < 0:
                return
            self._target = Target(
                self._targets[index, 1:3], movable=False, pen=pg.mkPen('r'), label=f"Target: {self._name}")
            self._target.setDepth(self._targets[index, 3])
            self._target.setVisible(True)
            self._parentPlot.addItem(self._target)
        if self._target is not None:
            self._target.setFocusDepth(depth)

    def getPosLabel(self) -> pg.ArrowItem:
        return self._arrow

    def setParent(self, parent):
        self._pastPlot.setParent(parent)
        self._presentPlot.setParent(parent)
        self._futurePlot.setParent(parent)
        self._label.setParent(parent)

    def deleteLater(self):
        self._arrow = None
        self._label.deleteLater()
        self._label = None
        self._presentPlot.deleteLater()
        self._presentPlot = None
        self._futurePlot.deleteLater()
        self._futurePlot = None
        self._pastPlot.deleteLater()
        self._pastPlot = None


class PipetteStateRegion(pg.LinearRegionItem):
    clicked = Qt.Signal(object)
    doubleclicked = Qt.Signal(object)

    def mouseClickEvent(self, ev: Qt.QGraphicsSceneMouseEvent):
        if ev.button() == Qt.Qt.LeftButton:
            self.clicked.emit(ev.pos())
            ev.accept()
        else:
            super().mouseClickEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.Qt.LeftButton:
            self.doubleclicked.emit(self)
            ev.accept()
        else:
            super().mouseDoubleClickEvent(ev)


class MultiPatchLogWidget(Qt.QWidget):
    # TODO selectable event types to display?
    # TODO images should be displayed as the timeline matches?
    # TODO option to add plots for anything else
    # TODO save initial target when log starts
    # TODO save device positions, orientation when log starts
    # TODO investigate what logging autopatch module does
    # TODO associate all images and recordings with the cell
    # TODO multipatch logs are one-per-cell
    # TODO they can reference each other?
    # TODO selectable cells, pipettes
    # TODO filter log messages by type
    # TODO record the patch profile params and any changes thereof
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
        self._frames = []
        self._pinned_image_z = -10000
        self._stretch_threshold = 0.005
        self._tear_threshold = -0.00128
        layout = Qt.QGridLayout()
        # TODO my layout skills suuuuuck
        self.setLayout(layout)
        self._plots_widget = pg.GraphicsLayoutWidget()
        self._widgets.append(self._plots_widget)
        layout.addWidget(self._plots_widget, 0, 0)
        self._visual_field = self._plots_widget.addPlot()
        self._visual_field.setAspectLocked(ratio=1.0001)  # workaround weird bug with qt
        self._resistance_plot = self._plots_widget.addPlot(
            name='Resistance', labels=dict(bottom='s', left='Ω'), row=1, col=0)
        self._analysis_plot = self._plots_widget.addPlot(name='Analysis', row=2, col=0)
        self._analysis_plot.addItem(
            pg.InfiniteLine(movable=False, pos=self._stretch_threshold, angle=0, pen=pg.mkPen('w')))
        self._analysis_plot.addItem(
            pg.InfiniteLine(movable=False, pos=self._tear_threshold, angle=0, pen=pg.mkPen('w')))
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
        ctrl_widget = Qt.QWidget()
        ctrl_widget.setMaximumWidth(200)
        self._ctrl_layout = Qt.QVBoxLayout()
        ctrl_widget.setLayout(self._ctrl_layout)
        self._buildCtrlUi()
        layout.addWidget(ctrl_widget, 0, 1)

    def _buildCtrlUi(self):
        self._ctrl_layout.addWidget(Qt.QLabel('Events:'))
        states = Qt.QCheckBox('State Changes')
        states.stateChanged.connect(self._toggleStateChanges)
        self._ctrl_layout.addWidget(states)
        status = Qt.QCheckBox('Status Messages')
        status.stateChanged.connect(self._toggleStatusMessages)
        self._ctrl_layout.addWidget(status)
        self._ctrl_layout.addWidget(Qt.QLabel('Plots:'))
        peak_resistance = Qt.QCheckBox('Peak Resistance')
        peak_resistance.stateChanged.connect(self._togglePeakResistance)
        self._ctrl_layout.addWidget(peak_resistance)
        steady_resistance = Qt.QCheckBox('Steady State Resistance')
        steady_resistance.stateChanged.connect(self._toggleSteadyResistance)
        self._ctrl_layout.addWidget(steady_resistance)
        analysis = Qt.QCheckBox('Analysis')
        analysis.stateChanged.connect(self._toggleAnalysis)
        self._ctrl_layout.addWidget(analysis)
        self._ctrl_layout.addWidget(Qt.QLabel('Stretch threshold:'))
        stretch_threshold_input = Qt.QLineEdit(f"{self._stretch_threshold:.6f}")
        stretch_threshold_input.editingFinished.connect(self._stretchThresholdChanged)
        self._ctrl_layout.addWidget(stretch_threshold_input)
        self._ctrl_layout.addWidget(Qt.QLabel('Tear threshold:'))
        tear_threshold_input = Qt.QLineEdit(f"{self._tear_threshold:.6f}")
        tear_threshold_input.editingFinished.connect(self._tearThresholdChanged)
        self._ctrl_layout.addWidget(tear_threshold_input)

    def _toggleStateChanges(self):
        pass

    def _toggleStatusMessages(self):
        pass

    def _stretchThresholdChanged(self):
        pass

    def _tearThresholdChanged(self):
        pass

    def _togglePeakResistance(self):
        pass

    def _toggleSteadyResistance(self):
        pass

    def _toggleAnalysis(self):
        pass

    def timeChanged(self, slider: pg.InfiniteLine):
        time = slider.getXPos()
        for p in self._pipettes:
            p.setTime(time)
        self._pinned_image_z = -10000
        for frame, img in self._frames:
            if frame <= time:
                img.setZValue(self._pinned_image_z)
                self._pinned_image_z += 1
            else:
                img.setZValue(-10000)

    def startTime(self) -> float:
        return min(log.firstTime() for log in self._logFiles) or 0

    def endTime(self) -> float:
        return max(log.lastTime() for log in self._logFiles) or 0

    def addLog(self, log: "FileHandle"):
        log_data: MultiPatchLogData = log.read()
        self._logFiles.append(log_data)
        if log.parent():
            self.loadImagesFromDir(log.parent().parent())
        self.loadImagesFromDir(log.parent())
        for dev in log_data.devices():
            path = log_data[dev]['position']
            states = log_data[dev]['state']
            test_pulses = log_data[dev]['test_pulse']
            if len(path) > 0:
                widget = PipettePathWidget(
                    dev, plot=self._visual_field, log_data=log_data, start_time=self.startTime())
                self._pipettes.append(widget)
            self.plotTestPulses(test_pulses, states)

        self._timeSlider.setBounds([0, self.endTime() - self.startTime()])
        self._resistance_plot.setXRange(0, self.endTime() - self.startTime())

    def plotTestPulses(self, test_pulses, states):
        from acq4.devices.PatchPipette.states import ResealAnalysis

        # TODO better colors?
        time = test_pulses['event_time'] - self.startTime()
        if len(time) > 0:
            self._resistance_plot.plot(
                time, test_pulses['steadyStateResistance'], pen=pg.mkPen('b'))
            # self._resistance_plot.plot(
            #     time, test_pulses['peakResistance'], pen=pg.mkPen('g'))
            # plot the exponential average as is used by the reseal logic
            analyzer = ResealAnalysis(self._stretch_threshold, self._tear_threshold, 4, 10)
            measurements = np.concatenate(
                (time[:, np.newaxis], test_pulses['steadyStateResistance'][:, np.newaxis]), axis=1)
            # break the analysis up by state changes
            state_times = [s[0] - self.startTime() for s in states if s[2] == '']
            start_indexes = np.searchsorted(time, state_times)
            start_indexes = np.concatenate(([0], start_indexes, [len(states)]))
            for i in range(len(start_indexes) - 1):
                start = start_indexes[i]
                end = start_indexes[i + 1]
                if start >= end - 1:
                    continue
                analysis = analyzer.process_measurements(measurements[start:end])
                self._analysis_plot.plot(analysis["time"], analysis["detect_ratio"], pen=pg.mkPen('b'))
                self._analysis_plot.plot(analysis["time"], analysis["repair_ratio"], pen=pg.mkPen(90, 140, 255))
                self._resistance_plot.plot(analysis["time"], analysis["detect_avg"], pen=pg.mkPen(80, 255, 120))
                self._resistance_plot.plot(analysis["time"], analysis["repair_avg"], pen=pg.mkPen(110, 255, 190))
                self._plotCenteredBooleans(analysis["time"], analysis["stretching"], 'g', 'x')
                self._plotCenteredBooleans(analysis["time"], analysis["tearing"], 'r', 'o')
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
                    status = state[2].replace('{', '{{').replace('}', '}}')
                    line.label = pg.InfLineLabel(
                        line, status, position=0.75, rotateAxis=(1, 0), anchor=(1, 1), color=color)
            if last_time is not None:
                brush = pg.mkBrush(pg.intColor(region_idx, hues=8, alpha=30))
                self._addRegion(last_time - self.startTime(), self.endTime() - self.startTime(), brush, last_state)

    def _plotCenteredBooleans(self, time, data, color, symbol):
        data = data.astype(float)
        data[data < 1] = np.nan
        data -= 1
        self._analysis_plot.plot(time, data, pen=pg.mkPen(color), symbol=symbol)

    def _addRegion(self, start, end, brush, label):
        region = PipetteStateRegion([start, end], movable=False, brush=brush)
        region.doubleclicked.connect(self._zoomToRegion)
        region.clicked.connect(self._setTimeFromClick)
        self._resistance_plot.addItem(region)
        pg.InfLineLabel(region.lines[0], label, position=0.5, rotateAxis=(1, 0), anchor=(1, 1))

    def _zoomToRegion(self, region: PipetteStateRegion):
        self._resistance_plot.setXRange(*region.getRegion(), padding=0)

    def _setTimeFromClick(self, pos: Qt.QPointF):
        self._timeSlider.setValue(pos.x())

    def loadImagesFromDir(self, directory: "DirHandle"):
        # TODO images associated with the correct slice and cell only
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
                self._frames.append((frame.info().get('time', 0) - self.startTime(), img))
        self._frames = sorted(self._frames, key=lambda x: x[0])

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
