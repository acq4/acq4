from __future__ import annotations

import json
import os
import re
from typing import Any

import h5py
import numpy as np

import pyqtgraph as pg
from pyqtgraph.units import GΩ, MΩ
from acq4.filetypes.FileType import FileType
from acq4.util import Qt
from acq4.util.functions import plottable_booleans
from acq4.util.target import Target
from neuroanalysis.test_pulse import PatchClampTestPulse
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

TEST_PULSE_METAARRAY_INFO = [
    {'name': 'event_time', 'type': 'float', 'units': 's'},
    {'name': 'baseline_potential', 'type': 'float', 'units': 'V'},
    {'name': 'baseline_current', 'type': 'float', 'units': 'A'},
    {'name': 'input_resistance', 'type': 'float', 'units': 'Ω'},
    {'name': 'access_resistance', 'type': 'float', 'units': 'Ω'},
    {'name': 'steady_state_resistance', 'type': 'float', 'units': 'Ω'},
    {'name': 'fit_amplitude', 'type': 'float'},
    {'name': 'time_constant', 'type': 'float'},
    {'name': 'fit_yoffset', 'type': 'float'},
    {'name': 'fit_xoffset', 'type': 'float', 'units': 's'},
    {'name': 'capacitance', 'type': 'float', 'units': 'F'},
    {'name': 'start_time', 'type': 'float', 'units': 's'},
]
TEST_PULSE_NUMPY_DTYPE = [(info['name'], info['type']) for info in TEST_PULSE_METAARRAY_INFO]
TEST_PULSE_PARAMETER_CONFIG = []
for info in TEST_PULSE_METAARRAY_INFO:
    info = info.copy()
    if 'units' in info:
        info['suffix'] = info['units']
        del info['units']
    TEST_PULSE_PARAMETER_CONFIG.append(info)


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
        self._devices = {}
        self.fullTestPulseStacks: dict[str, H5BackedTestPulseStack] = {}
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
            if event_type in {'auto_bias_change'}:
                uses.append('auto_bias_change')
            if event_type in {'target_changed'}:
                uses.append('target')
            # currently ignored:
            # if event_type in {'move_requested'}:
            #     uses.append('move_request')
            if event_type in {'test_pulse'}:
                uses += ['test_pulse', 'full_test_pulse']
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
                if 'full_test_pulse' in self._devices[dev]:
                    h5_fns = {loc.split(":")[0] for loc in self._devices[dev]['full_test_pulse'] if loc}
                    for h5_fn in h5_fns:
                        h5_fn = os.path.join(os.path.dirname(filename), h5_fn)
                        # TODO only open the file once, not once per device
                        h5_file = h5py.File(h5_fn, 'r')
                        # TODO find a way to stop duplicating the "test_pulses/{dev}" part
                        data_group = h5_file[f"test_pulses/{dev}"]
                        stack = H5BackedTestPulseStack(data_group)
                        if dev in self.fullTestPulseStacks:
                            self.fullTestPulseStacks[dev].merge(stack)
                        else:
                            self.fullTestPulseStacks[dev] = stack

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
            'state': list(range(count_for_use('state'))),
            'auto_bias_change': np.zeros(
                (count_for_use('auto_bias_change'), 2),
                dtype=float,
            ),
            'target': np.zeros(
                (count_for_use('target'), 4),
                dtype=float,
            ),
            # TODO save field of view dimensions to show stage (camera) position
            # TODO save objective
            # TODO save current patch profile and any changes thereof
            # TODO save pressure measurements, maybe?
            # TODO save lighting
            # TODO save clamp_state_change, holding voltage
            # TODO save entire test pulse
            'test_pulse': np.zeros(
                count_for_use('test_pulse'),
                dtype=TEST_PULSE_NUMPY_DTYPE,
            ),
            'full_test_pulse': list(range(count_for_use('full_test_pulse'))),
        }

    @staticmethod
    def _prepare_event_for_use(event: dict, use: str) -> tuple[Any, ...]:
        event_time = float(event['event_time'])
        # TODO 'move_request'
        # TODO 'init'
        if use == 'event':
            return event_time, event['event'], event['is_true']
        if use == 'position':
            return event_time, *event.get('position', event.get('globalPosition', (np.nan, np.nan, np.nan)))
        if use == 'pressure':
            return event_time, event['pressure'], event['source']
        if use == 'state':
            return event_time, event['state'], event.get('info', '')
        if use == 'auto_bias_change':
            return event_time, event['target'] if event.get('enabled', True) else np.nan
        if use == 'target':
            return event_time, *event['target_position']
        # if use == 'move_request':
        #     return event_time, event['opts']
        if use == 'test_pulse':
            return tuple(event[info['name']] for info in TEST_PULSE_METAARRAY_INFO)
        if use == 'full_test_pulse':
            return event.get('full_test_pulse')


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
            log_data: dict[str, Any],
            start_time: float,
    ):
        self._name = name
        self._parentPlot = plot
        path = log_data['position'][:]
        path[:, 0] -= start_time
        self._path = path
        states = log_data['state']
        self._states = [[s[0] - start_time, *s[1:]] for s in states]
        self._targets = log_data['target'][:]
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

        if state := next((s for s in self._states[::-1] if s[0] < time), None):
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
    # TODO display video files
    # TODO save initial target when log starts
    # TODO save device orientation when log starts
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
        self._current_time = 0
        self._pinned_image_z = -10000
        layout = Qt.QGridLayout()
        self.setLayout(layout)
        self._plots_widget = pg.GraphicsLayoutWidget()
        self._widgets.append(self._plots_widget)
        layout.addWidget(self._plots_widget, 0, 0)
        self._visual_field = self._plots_widget.addPlot()
        self._visual_field.setAspectLocked(ratio=1.0001)  # workaround weird bug with qt
        self._full_test_pulse_plot = None
        self._test_pulse_label = None
        self._plots_by_units: dict[str, pg.PlotItem] = {}
        self._regions_by_plot: dict[pg.PlotItem, list[PipetteStateRegion]] = {}
        self._status_by_plot: dict[pg.PlotItem, list[pg.InfiniteLine]] = {}
        self._plot_items_by_plot: dict[pg.PlotItem, list[pg.PlotDataItem]] = {}
        self._devices = {}
        self._full_test_pulse_stacks = {}
        self._time_sliders = []
        ctrl_widget = Qt.QWidget(self)
        ctrl_widget.setMaximumWidth(200)
        self._ctrl_layout = Qt.QVBoxLayout()
        ctrl_widget.setLayout(self._ctrl_layout)
        self._buildCtrlUi()
        layout.addWidget(ctrl_widget, 0, 1)

    def buildPlotForUnits(self, units: str) -> pg.PlotItem:
        if units in self._plots_by_units:
            return self._plots_by_units[units]
        plot: pg.PlotItem = self._plots_widget.addPlot(
            name=units,
            labels=dict(bottom=('time', 's'), left=('', units)),
            row=len(self._plots_by_units) + 2,
            col=0,
        )
        plot.addLegend()
        if self._plots_by_units:
            plot.setXLink(self._plots_by_units[list(self._plots_by_units.keys())[0]])
        else:
            plot.setXRange(0, self.endTime() - self.startTime())
        time_slider = pg.InfiniteLine(
            movable=True,
            angle=90,
            pen=pg.mkPen('r'),
            hoverPen=pg.mkPen('w', width=2),
            label='t={value:0.2f}s',
            labelOpts={'position': 0.1, 'color': pg.mkColor('r'), 'movable': True},
        )
        time_slider.sigPositionChanged.connect(self.timeChanged)
        time_slider.setBounds([0, self.endTime() - self.startTime()])
        time_slider.setValue(self._current_time)
        plot.addItem(time_slider)
        self._time_sliders.append(time_slider)
        if self._display_state_regions.isChecked():
            regions = self._addStateRegions(plot)
            self._regions_by_plot[plot] = regions
        if self._display_status.isChecked():
            lines = self._addStatusMessages(plot)
            self._status_by_plot[plot] = lines
        plot.show()
        self._plots_by_units[units] = plot
        return plot

    def _addStateRegions(self, plot) -> list[PipetteStateRegion]:
        regions = []
        for data in self._devices.values():
            last_time = None
            last_state = None
            region_idx = 0
            for state in data.get('state', []):
                if state[2] == '':
                    brush = pg.mkBrush(pg.intColor(region_idx, hues=8, alpha=30))
                    if last_time is not None:
                        region = self._makeStateRegion(
                            last_time - self.startTime(), state[0] - self.startTime(), brush, last_state)
                    else:
                        region = self._makeStateRegion(0, state[0] - self.startTime(), brush, '')
                    plot.addItem(region)
                    regions.append(region)
                    region_idx += 1
                    last_time = state[0]
                    last_state = state[1]
            if last_time is not None:
                brush = pg.mkBrush(pg.intColor(region_idx, hues=8, alpha=30))
                region = self._makeStateRegion(
                    last_time - self.startTime(), self.endTime() - self.startTime(), brush, last_state)
                plot.addItem(region)
                regions.append(region)
        return regions

    def _addStatusMessages(self, plot) -> list[pg.InfiniteLine]:
        color = pg.mkColor(255, 255, 255, 80)
        lines = []
        for data in self._devices.values():
            for state in data.get('state', []):
                if state[2] != '':
                    line = pg.InfiniteLine(movable=False, pos=state[0] - self.startTime(), angle=90,
                                           pen=pg.mkPen(color))
                    plot.addItem(line)
                    status = state[2].replace('{', '{{').replace('}', '}}')
                    line.label = pg.InfLineLabel(
                        line, status, position=0.75, rotateAxis=(1, 0), anchor=(1, 1), color=color)
                    lines.append(line)
        return lines

    def _buildCtrlUi(self):
        # TODO color picker for each plot
        # TODO devices
        # self._ctrl_layout.addWidget(Qt.QLabel('Devices:'))
        self._ctrl_layout.addWidget(Qt.QLabel('Events:'))
        self._display_state_regions = Qt.QCheckBox('State Changes')
        self._display_state_regions.toggled.connect(self._toggleDisplayStateRegions)
        self._ctrl_layout.addWidget(self._display_state_regions)
        self._display_status = Qt.QCheckBox('Status Messages')
        self._display_status.toggled.connect(self._toggleDisplayStatus)
        self._ctrl_layout.addWidget(self._display_status)
        self._ctrl_layout.addWidget(Qt.QLabel('Plots:'))
        self._testPulseAnalysisCheckboxes = []
        for meta in TEST_PULSE_METAARRAY_INFO:
            if meta['name'] == 'event_time':
                continue
            name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', meta['name']).title()
            cb = Qt.QCheckBox(name)
            cb.name = meta['name']
            cb.toggled.connect(self._toggleTestPulseAnalysisPlot)
            self._testPulseAnalysisCheckboxes.append(cb)
            self._ctrl_layout.addWidget(cb)
        self._displayPressure = Qt.QCheckBox('Pressure')
        self._displayPressure.toggled.connect(self._togglePressurePlot)
        self._ctrl_layout.addWidget(self._displayPressure)
        self._sealAnalysisItems = {}
        self._displaySealAnalysis = Qt.QCheckBox('Seal Analysis')
        self._displaySealAnalysis.toggled.connect(self._toggleSealAnalysis)
        self._ctrl_layout.addWidget(self._displaySealAnalysis)
        self._resealAnalysisItems = {}
        self._displayResealAnalysis = Qt.QCheckBox('Reseal Analysis')
        self._displayResealAnalysis.toggled.connect(self._toggleResealAnalysis)
        self._ctrl_layout.addWidget(self._displayResealAnalysis)
        self._detectAnalysisItems = {}
        self._displayDetectAnalysis = Qt.QCheckBox('Cell Detect Analysis')
        self._displayDetectAnalysis.toggled.connect(self._toggleDetectAnalysis)
        self._ctrl_layout.addWidget(self._displayDetectAnalysis)
        self._displayFullTestPulse = Qt.QCheckBox('Full Test Pulse Data')
        self._displayFullTestPulse.toggled.connect(self._toggleFullTestPulse)
        self._ctrl_layout.addWidget(self._displayFullTestPulse)

    def _toggleDisplayStateRegions(self, state: bool):
        for plot in self._plots_by_units.values():
            if state:
                regions = self._addStateRegions(plot)
                self._regions_by_plot.setdefault(plot, []).extend(regions)
            else:
                for region in self._regions_by_plot.get(plot, []):
                    plot.removeItem(region)
                self._regions_by_plot[plot] = []

    def _toggleDisplayStatus(self, state: bool):
        for plot in self._plots_by_units.values():
            if state:
                lines = self._addStatusMessages(plot)
                self._status_by_plot.setdefault(plot, []).extend(lines)
            else:
                for line in self._status_by_plot.get(plot, []):
                    plot.removeItem(line)
                self._status_by_plot[plot] = []

    def _toggleTestPulseAnalysisPlot(self, state: bool):
        ev = self.sender()
        meta = next(m for m in TEST_PULSE_METAARRAY_INFO if m['name'] == ev.name)
        plot = self.buildPlotForUnits(meta.get('units', ''))
        if state:
            for data in self._devices.values():
                test_pulses = data.get('test_pulse', np.zeros(0, dtype=TEST_PULSE_NUMPY_DTYPE))
                time = test_pulses['event_time'] - self.startTime()
                if len(time) > 0:
                    idx = next(i for i, m in enumerate(TEST_PULSE_METAARRAY_INFO) if m['name'] == ev.name)
                    plot_item = plot.plot(
                        time,
                        test_pulses[ev.name],
                        pen=pg.mkPen((idx, len(TEST_PULSE_NUMPY_DTYPE))),
                        name=ev.name,
                    )
                    self._plot_items_by_plot.setdefault(plot, []).append(plot_item)
        else:
            for item in self._plot_items_by_plot.get(plot, []):
                plot.removeItem(item)
            self._plot_items_by_plot[plot] = []

    def _togglePressurePlot(self, state: bool):
        if state:
            plot = self.buildPlotForUnits('Pa')
            plot.show()
            for data in self._devices.values():
                pressure = data.get('pressure', np.zeros(0, dtype=[('time', float), ('pressure', float)]))
                time = pressure['time'] - self.startTime()
                if len(time) > 0:
                    plot.plot(time, pressure['pressure'], pen=pg.mkPen((0, len(TEST_PULSE_NUMPY_DTYPE))), name='Pressure')
        elif 'Pa' in self._plots_by_units:
            self._plots_by_units['Pa'].hide()

    def _toggleAnalysis(self, cls, analysisItems: dict, state: bool, *args, **kwargs):
        if state:
            for units, items in cls.plot_items(*args, **kwargs).items():
                plot = self.buildPlotForUnits(units)
                analysisItems.setdefault(units, []).extend(items)
                for item in items:
                    plot.addItem(item)
            measurements = self.testPulseAnalysisDataByState('steady_state_resistance')
            for units, plots in cls.plots_for_data(measurements, *args, **kwargs).items():
                plot = self.buildPlotForUnits(units)
                analysisItems.setdefault(units, [])
                for p in plots:
                    analysisItems[units].append(plot.plot(**p))
        else:
            for units, items in analysisItems.items():
                plot = self._plots_by_units.get(units)
                if plot is not None:
                    for item in items:
                        plot.removeItem(item)
            analysisItems.clear()

    def _toggleSealAnalysis(self, state: bool):
        from acq4.devices.PatchPipette.states import SealAnalysis

        # TODO get the current patch profile params
        self._toggleAnalysis(SealAnalysis, self._sealAnalysisItems, state, tau=5, success_at=1*GΩ, hold_at=100*MΩ)

    def _toggleResealAnalysis(self, state: bool):
        from acq4.devices.PatchPipette.states import ResealAnalysis

        # TODO get the current patch profile params
        self._toggleAnalysis(
            ResealAnalysis,
            self._resealAnalysisItems,
            state,
            stretch_threshold=0.005,
            tear_threshold=-0.00128,
            detection_tau=5,
            repair_tau=10,
        )

    def _toggleDetectAnalysis(self, state: bool):
        from acq4.devices.PatchPipette.states import CellDetectAnalysis

        # TODO get the current patch profile params
        self._toggleAnalysis(
            CellDetectAnalysis,
            self._detectAnalysisItems,
            state,
            baseline_tau=20,
            cell_threshold_fast=1e6,
            cell_threshold_slow=200e3,
            slow_detection_steps=3,
            obstacle_threshold=1e6,
            break_threshold=-1e6,
        )

    def testPulseAnalysisDataByState(self, field: str):
        for data in self._devices.values():
            test_pulses = data.get('test_pulse', np.zeros(0, dtype=TEST_PULSE_NUMPY_DTYPE))
            states = data.get('state', [])
            time = test_pulses['event_time'] - self.startTime()
            if len(time) > 0:
                measurements = np.concatenate(
                    (time[:, np.newaxis], test_pulses[field][:, np.newaxis]), axis=1)
                # break the analysis up by state changes
                state_times = [s[0] - self.startTime() for s in states if s[2] == '']
                start_indexes = np.searchsorted(time, state_times)
                start_indexes = np.concatenate(([0], start_indexes, [len(states)]))
                for i in range(len(start_indexes) - 1):
                    start = start_indexes[i]
                    end = start_indexes[i + 1]
                    if start >= end - 1:
                        continue
                    yield measurements[start:end]

    def _toggleFullTestPulse(self, state: bool):
        if state:
            # hint: to save a test pulse for use in e.g. unit tests:
            #    import h5py
            #    from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack
            #
            #    widget = man.getModule("Data Manager").ui.dataViewWidget._multiPatchLogWidget
            #    tp = widget.testPulsesAtTime(SOMETIME)['PatchPipette1']
            #    f = h5py.File("/WHEREVER/THIS/IS/neuroanalysis/test_data/TP_NAME.h5", "a")
            #    gr = f.create_group("test_pulses")
            #    tps = H5BackedTestPulseStack(gr)
            #    tps.append(tp)
            #    f.close()
            #    del(tps)
            #    del(gr)

            self._full_test_pulse_plot = self._plots_widget.addPlot(
                name="Test Pulse",
                title='Test Pulse',
                labels=dict(bottom=('time', 's'), left=('', 'V')),
                row=1,
                col=0,
            )
            self._full_test_pulse_plot.addLegend()
            self._displayTestPulseDataAtTime(self._current_time)
        else:
            self._plots_widget.removeItem(self._full_test_pulse_plot)
            self._full_test_pulse_plot = None

    def _displayTestPulseDataAtTime(self, when):
        plot = self._full_test_pulse_plot
        if plot is None:
            return
        plot.clear()
        if self._test_pulse_label is not None:
            plot.vb.removeItem(self._test_pulse_label)
            self._test_pulse_label = None

        if tps := self.testPulsesAtTime(when):
            tp = list(tps.values())[0]  # todo separate plots for each device
            tp.plot(plot, label=False)
            self._test_pulse_label = tp.label_for_plot(plot)
            plot.setLabel('left', tp.plot_title, tp.plot_units)

    def testPulsesAtTime(self, when) -> dict[str, PatchClampTestPulse]:
        abs_when = when + self.startTime()
        possibilities = {dev: stack.at_time(abs_when) for dev, stack in self._full_test_pulse_stacks.items()}
        return {dev: tp for dev, tp in possibilities.items() if tp is not None}

    def timeChanged(self, slider: pg.InfiniteLine):
        self.setTime(slider.getXPos())

    def setTime(self, time: float):
        self._current_time = time
        for p in self._pipettes:
            p.setTime(time)
        self._pinned_image_z = -10000
        for slider in self._time_sliders:
            slider.setValue(time)
        for frame, img in self._frames:
            if frame <= time:
                img.show()
                img.setZValue(self._pinned_image_z)
                self._pinned_image_z += 1
            else:
                img.hide()
        self._displayTestPulseDataAtTime(time)

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
            self._devices[dev] = log_data[dev]
            stack = log_data.fullTestPulseStacks.get(dev, None)
            if stack is None:
                continue
            if dev in self._full_test_pulse_stacks:
                self._full_test_pulse_stacks[dev].merge(stack)
            else:
                self._full_test_pulse_stacks[dev] = stack
        self.redraw()

    def redraw(self):
        # TODO clear things first
        for dev, data in self._devices.items():
            path = data['position']
            if len(path) > 0:
                widget = PipettePathWidget(
                    dev, plot=self._visual_field, log_data=data, start_time=self.startTime())
                self._pipettes.append(widget)

        for slider in self._time_sliders:
            slider.setBounds([0, self.endTime() - self.startTime()])
        for plot in self._plots_by_units.values():
            plot.setXRange(0, self.endTime() - self.startTime())
            break  # they should be x-linked
        self.setTime(0)

    def _makeStateRegion(self, start, end, brush, label) -> PipetteStateRegion:
        region = PipetteStateRegion([start, end], movable=False, brush=brush)
        region.doubleclicked.connect(self._zoomToRegion)
        region.clicked.connect(self._setTimeFromClick)
        pg.InfLineLabel(region.lines[0], label, position=0.5, rotateAxis=(1, 0), anchor=(1, 1))
        return region

    def _zoomToRegion(self, region: PipetteStateRegion):
        # x-linked plots, so only the first needs to be set
        list(self._plots_by_units.values())[0].setXRange(*region.getRegion(), padding=0)

    def _setTimeFromClick(self, pos: Qt.QPointF):
        for slider in self._time_sliders:
            slider.setValue(pos.x())

    def loadImagesFromDir(self, directory: "DirHandle"):
        # TODO images associated with the correct slice and cell only
        for frame in directory.representativeFramesForAllImages():
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
