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
            'state': np.zeros(
                count_for_use('state'),
                dtype=[('time', float), ('state', 'U32'), ('info', 'U128')],  # TODO maybe not numpy?
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
        if use == 'state':
            return event['event_time'], event['state'], event.get('info', '')
        if use == 'auto_bias_target':
            return event['event_time'], event['target'] if event.get('enabled', True) else np.nan
        if use == 'target':
            return event['event_time'], *event['target_position']
        # if use == 'move_request':
        #     return event['event_time'], event['opts']
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


class PipettePathWidget(Qt.QWidget):
    def __init__(self, name: str, parent=None, path: np.ndarray=None):
        super().__init__(parent)
        self._name = name
        self._path = path
        # TODO time as color
        self._plot = pg.PlotDataItem(self._path[:, 1], self._path[:, 2], pen=pg.mkPen('b', width=2))
        self._arrow = pg.ArrowItem(pen=pg.mkPen('b', width=2))
        self._arrow.setPos(self._path[0, 1], self._path[0, 2])
        self._label = pg.TextItem(text=name, color=pg.mkColor('b'))
        self._label.setParentItem(self._arrow)

    def getPlot(self) -> pg.PlotDataItem:
        return self._plot

    def setTime(self, time: float):
        """Move the arrow to the interpolated position at the given time."""
        pos = self._path[self._path[:, 0] <= time][-1]
        self._arrow.setPos(pos[1], pos[2])

    def getPosLabel(self) -> pg.ArrowItem:
        return self._arrow

    def deleteLater(self):
        self._plot.setParent(None)
        self._plot.deleteLater()
        super().deleteLater()


class MultiPatchLogWidget(Qt.QWidget):
    # TODO look at canvas
    # TODO add plot of events on timeline (tags?)
    #    selectable event types to display?
    # TODO images saved in this directory should be displayed as the timeline matches?
    # TODO option to add plots for anything else
    # TODO add target position
    # TODO add pipette position (and paths?)
    #    we don't poll the position, so the movement requests are all we have
    # TODO investigate what logging autopatch module does
    # TODO associate all images and recordings with the cell
    # TODO multipatch logs are one-per-cell
    # TODO they can reference each other?
    # TODO widget should be able to handle multiple log files
    # TODO selectable cells, pipettes
    # TODO filter log messages by type
    # TODO raw log? just events on the time plot may be enough
    # TODO don't try to display position Z
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logFiles = []
        self._pipettes: list[PipettePathWidget] = []
        self._cells = []
        self._events = []
        self._widgets = []
        self._pinned_image_z = -10000
        self._timeSliderResolution = 10.  # 10 ticks per second on the time slider
        self._layout = Qt.QVBoxLayout()
        self.setLayout(self._layout)
        self._visual_field = pg.GraphicsLayoutWidget()
        self._widgets.append(self._visual_field)
        self._layout.addWidget(self._visual_field)
        self._plot = self._visual_field.addPlot(title="")

        self._timeSlider = Qt.QSlider()
        self._layout.addWidget(self._timeSlider)
        self._timeSlider.setOrientation(Qt.Qt.Horizontal)
        self._timeSlider.setMinimum(0)
        self._timeLabel = Qt.QLabel()
        self._layout.addWidget(self._timeLabel)
        self._timeSlider.valueChanged.connect(self.timeChanged)

    def timeChanged(self, time: int):
        time = self._sliderToTime(time)
        self._timeLabel.setText(f"{time} s")
        for p in self._pipettes:
            p.setTime(time)

    def _sliderToTime(self, slider: int) -> float:
        return (slider / self._timeSliderResolution) + self.startTime()

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
            widget = PipettePathWidget(dev, path=path)
            self._pipettes.append(widget)
            self._plot.addItem(widget.getPlot())
            self._plot.addItem(widget.getPosLabel())
        self._timeSlider.setMaximum(int((self.endTime() - self.startTime()) * self._timeSliderResolution))

    def loadImagesFromDir(self, directory: "DirHandle"):
        # TODO images associated with the correct slice and cell only
        # TODO integrate with time-slider to set the Z values
        from acq4.util.imaging import Frame

        for f in directory.ls():
            if f.endswith('.tif'):
                f = directory[f]
                frame = Frame(f.read(), f.info().deepcopy())
                frame.loadLinkedFiles(directory)
                img = frame.imageItem()
                img.setZValue(self._pinned_image_z)
                self._pinned_image_z += 1
                self._plot.addItem(img)

    def clear(self):
        for w in self._widgets:
            w.setParent(None)
            w.deleteLater()
        self._widgets = []
        for p in self._pipettes:
            p.deleteLater()
        self._pipettes = []
