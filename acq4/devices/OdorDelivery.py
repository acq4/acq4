from collections import namedtuple

import math
import numpy as np
import threading
from datetime import datetime
from time import sleep
from typing import Union, List, Dict, Tuple

from pyqtgraph import PlotWidget, intColor, mkPen
from pyqtgraph.parametertree import ParameterTree
from pyqtgraph.parametertree.parameterTypes import GroupParameter, ListParameter
from .Device import Device, TaskGui, DeviceTask
from ..util import Qt
from ..util.future import Future
from ..util.generator.StimParamSet import SeqParameter


class OdorDelivery(Device):
    """
    Device class representing an odor delivery device. Config should include a section describing all the possible
    odors in the following format::

        odors:
            first channel name:
                channel: 0
                ports:
                    2: 'first odor name'
                    4: 'second odor name'
                    ...
            second channel name:
                channel: 1
                ports:
                    2: 'first odor name'
                    4: 'second odor name'
                    ...
            ...
    """
    odors: "dict[str, dict[str, Union[int, dict[int, str]]]]"

    def __init__(self, deviceManager, config: dict, name: str):
        super().__init__(deviceManager, config, name)
        self.odors = {
            group: {
                "channel": int(group_config["channel"]),
                "ports": {int(port): name for port, name in group_config["ports"].items()},
            }
            for group, group_config in config.get("odors", {}).items()
        }

    def odorChannels(self) -> List[int]:
        return sorted([gr["channel"] for gr in self.odors.values()])

    def odorDetails(self, odor: Tuple[int, int]) -> str:
        for chan_name in self.odors:
            if self.odors[chan_name]["channel"] == odor[0]:
                port_name = self.odors[chan_name]["ports"][odor[1]]
                return f"{chan_name}: {port_name}"
        raise ValueError(f"Invalid odor specification: {odor}")

    def odorsAsParameterLimits(self) -> Dict[str, Tuple[int, int]]:
        return {
            f"{chanName}[{port}]: {name}": (chanOpts["channel"], port)
            for chanName, chanOpts in self.odors.items()
            for port, name in chanOpts["ports"].items()
        }

    def channelName(self, channel: int) -> str:
        for chan_name in self.odors:
            if self.odors[chan_name]["channel"] == channel:
                return chan_name
        raise ValueError(f"Invalid channel: {channel}")

    def setChannelValue(self, channel: int, value: int) -> None:
        """Turn a given odor channel value"""
        raise NotImplementedError()

    def setAllChannelsOff(self) -> None:
        """Turn off all odors. (Reimplement if that should be handled other than by iterating)"""
        for ch in self.odorChannels():
            self.setChannelValue(ch, 0)

    def deviceInterface(self, win):
        return OdorDevGui(self)

    def taskInterface(self, task):
        return OdorTaskGui(self, task)

    def createTask(self, cmd, parentTask):
        """cmd will be coming in from the TaskGui.generateTask with whatever data I want it to have"""
        return OdorTask(self, cmd, parentTask)


class OdorDevGui(Qt.QWidget):
    """
    Take the {group_name: {channel: odor_name, ...}, ...} odors and make a ui that:
     * lets user select which group is in right now
     * lets user turn on/off odors
     * lets user set the intensity value
    """

    OFF_LABEL = "OFF"

    def __init__(self, dev: OdorDelivery):
        super().__init__()
        # TODO configuration option for being able to activate multiple channels at the same time
        self.dev = dev
        self.layout = Qt.FlowLayout()
        self.setLayout(self.layout)
        self._buttonGroups = {}
        self._groupButtons = {}
        self._controlButtons = {}
        self._setupOdorButtons()

    def _setupOdorButtons(self):
        first = True
        for group_name, group_config in self.dev.odors.items():
            channel = group_config["channel"]
            group_box = Qt.QGroupBox(f"{channel}: {group_name}")
            self._groupButtons[group_name] = group_box
            group_box.setObjectName(group_name)
            group_box.toggled.connect(self._handleChannelButtonPush)
            group_box.setCheckable(True)
            group_layout = Qt.FlowLayout()
            group_box.setLayout(group_layout)
            self.layout.addWidget(group_box)
            button_group = Qt.QButtonGroup()
            self._buttonGroups[group_name] = button_group

            def _add_button(btn):
                group_layout.addWidget(btn)
                button_group.addButton(btn)
                btn.clicked.connect(self._handleOdorButtonPush)

            if 1 not in group_config["ports"]:
                control_button = Qt.QRadioButton(f"{channel}[1]: Control")
                control_button.setObjectName(f"{channel}:1")
                control_button.setChecked(True)
                _add_button(control_button)

                self._controlButtons[group_name] = control_button

            for port, odor in group_config["ports"].items():
                if port == 0:  # Off is handled by group_box
                    continue
                button = Qt.QRadioButton(f"{channel}[{port}]: {odor}")
                button.setObjectName(f"{channel}:{port}")
                _add_button(button)
                if port == 1:
                    self._controlButtons[group_name] = button
                    button.setChecked(True)
            group_box.setChecked(False)  # needed to guarantee toggle signal
            group_box.setChecked(first)
            first = False

    def _handleChannelButtonPush(self, enabled):
        btn = self.sender()
        group_name = btn.objectName()
        channel = self.dev.odors[group_name]["channel"]
        self.dev.setChannelValue(channel, 1 if enabled else 0)
        if enabled:
            for button in self._buttonGroups[group_name].buttons():
                if button.isChecked():
                    channel, port = map(int, button.objectName().split(":"))
                    if port != 1:
                        self.dev.setChannelValue(channel, port)
            for group in self._groupButtons:
                if group != group_name:
                    self._groupButtons[group].setChecked(False)
        else:
            self._controlButtons[group_name].setChecked(True)

    def _handleOdorButtonPush(self):
        btn = self.sender()
        channel, port = map(int, btn.objectName().split(":"))
        self.dev.setChannelValue(channel, port)


class _ListSeqParameter(ListParameter):
    def __init__(self, **kwargs):
        kwargs["expanded"] = kwargs.get("expanded", False)
        super().__init__(**kwargs)
        initialParams = [p.name() for p in self]
        sequence_names = ["off", "select"]
        newParams = [
            {"name": "sequence", "type": "list", "value": "off", "limits": sequence_names},
            {"name": "select", "type": "checklist", "visible": False, "limits": kwargs["limits"], "exclusive": False},
            {"name": "randomize", "type": "bool", "value": False, "visible": False},
        ]
        self.visibleParams = {  # list of params to display in each mode
            "off": initialParams + ["sequence"],
            "select": initialParams + ["sequence", "select", "randomize"],
        }
        if "group_by" in kwargs:
            for name, fn in kwargs["group_by"].items():
                grouping = {}
                for n, v in kwargs["limits"].items():
                    grouping.setdefault(fn(n, v), []).append(v)
                sequence_names.append(name)
                newParams.append({"name": name, "type": "list", "visible": False, "limits": grouping})
                self.visibleParams[name] = initialParams + ["sequence", name, "randomize"]

        for ch in newParams:
            self.addChild(ch)

    def compile(self):
        name = f"{self.parent().name()}_{self.name()}"
        mode = self["sequence"]
        if mode == "select":
            seq = self["select"]
        elif mode == "off":
            seq = []
        else:  # arbitrarily-named groupings
            seq = self[mode]
        if self["randomize"]:
            np.random.shuffle(seq)
        return name, seq

    def setState(self, state):
        for k in state:
            self[k] = state[k]
            self.param(k).setDefault(state[k])

    def getState(self):
        state = {}
        for ch in self:
            if not ch.opts["visible"]:
                continue
            name = ch.name()
            val = ch.value()
            if val is False:
                continue
            state[name] = val
        state["value"] = self.value()
        return state

    def treeStateChanged(self, param, changes):
        # catch changes to 'sequence' so we can hide/show other params.
        # Note: it would be easier to just catch self.sequence.sigValueChanged,
        # but this approach allows us to block tree change events, so they are all
        # released as a single update.
        with self.treeChangeBlocker():
            # queue up change
            ListParameter.treeStateChanged(self, param, changes)

            # if needed, add some more changes before releasing the signal
            for param, change, data in changes:
                # if the sequence value changes, hide/show other parameters
                if param is self.param("sequence") and change == "value":
                    vis = self.visibleParams[self["sequence"]]
                    for ch in self:
                        if ch.name() in vis:
                            ch.show()
                        else:
                            ch.hide()


class OdorEventParameter(GroupParameter):
    def varName(self):
        return self.name().replace(' ', '_')


class OdorTaskGui(TaskGui):
    _events: List[OdorEventParameter]

    def __init__(self, dev: OdorDelivery, taskRunner):
        super().__init__(dev, taskRunner)
        self._events = []
        self._next_event_number = 0
        self.taskRunner.sigTaskChanged.connect(self._redrawPlot)
        layout = Qt.QHBoxLayout()
        self.setLayout(layout)
        splitter = Qt.QSplitter()
        splitter.setOrientation(Qt.Qt.Horizontal)
        splitter.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._params = GroupParameter(name="Odor Events", addText="Add Odor Event")
        self._params.sigTreeStateChanged.connect(self._redrawPlot)
        self._params.sigAddNew.connect(self._addNewOdorEvent)
        ptree = ParameterTree()
        ptree.addParameters(self._params)
        splitter.addWidget(ptree)

        self._plot = PlotWidget()
        splitter.addWidget(self._plot)

        # TODO validate if the events will go longer than the total task runner

    def _addNewOdorEvent(self) -> OdorEventParameter:  # ignore signal args: self, typ
        ev = OdorEventParameter(name=f"Event {self._next_event_number}", removable=True)
        self._next_event_number += 1
        ev.addChildren(
            [
                SeqParameter(name="Start Time", type="float", limits=(0, None), units="s", siPrefix=True),
                SeqParameter(name="Duration", type="float", limits=(0, None), units="s", siPrefix=True, value=0.1),
                _ListSeqParameter(
                    name="Odor",
                    type="list",
                    limits=self.dev.odorsAsParameterLimits(),
                    group_by={"channel": lambda name, address: self.dev.channelName(address[0])},
                ),
            ]
        )

        self._params.addChild(ev)
        self._events.append(ev)
        ev.sigRemoved.connect(self._handleEventRemoval)
        self._redrawPlot()
        return ev

    def _handleEventRemoval(self, event):
        self._events = [ev for ev in self._events if ev != event]
        self.sigSequenceChanged.emit(self.dev.name())

    def _redrawPlot(self):
        self._plot.clear()
        chan_names = {conf["channel"]: chan for chan, conf in self.dev.odors.items()}
        self._plot.addLegend()
        if self._events:
            chans_in_use = {ev["Odor"][0] for ev in self._events if ev["Odor"]}

            def get_precision(a):
                if a == 0:
                    return 0
                return int(math.log10(float(str(a)[::-1]))) + 1

            precision = max(get_precision(ev["Duration"]) for ev in self._events)
            precision = max([precision, max(get_precision(ev["Start Time"]) for ev in self._events)])
            MIN_PRECISION = 3
            MAX_PRECISION = 10
            precision = max([MIN_PRECISION, min([MAX_PRECISION, precision])])
            task_duration = self.taskRunner.getParam("duration")
            point_count = int(task_duration * (10 ** precision)) + 1
            arrays = {
                chan: (np.ones(point_count, dtype=int) if chan in chans_in_use else np.zeros(point_count, dtype=int))
                for chan in chan_names
            }
            for ev in self._events:
                start = int(ev["Start Time"] * (10 ** precision))
                length = int(ev["Duration"] * (10 ** precision))
                if ev["Odor"]:
                    chan, val = ev["Odor"]
                    end = min((start + length, point_count))
                    arrays[chan][start:end] &= 0xFE  # turn off control (1) for the duration
                    arrays[chan][start:end] |= val
            time_vals = np.linspace(0, task_duration, point_count)
            for chan, arr in arrays.items():
                self._plot.plot(time_vals, arr, name=chan_names[chan], pen=mkPen(color=intColor(chan, max(arrays) + 1)))
        self.sigSequenceChanged.emit(self.dev.name())

    def saveState(self):
        return [ev.saveState(filter="user") for ev in self._events]

    def restoreState(self, state):
        for eventState in state:
            ev = self._addNewOdorEvent()
            ev.restoreState(eventState)
        self._redrawPlot()

    def generateTask(self, params=None):
        if params is None:
            params = {}
        paramSpace = self.listSequence()
        params = {k: paramSpace[k][v] for k, v in params.items()}
        for ev in self._events:
            params.setdefault(f"{ev.name()} Start Time", ev["Start Time"])
            params.setdefault(f"{ev.name()} Duration", ev["Duration"])
            params.setdefault(f"{ev.name()} Odor", ev["Odor"])
        return params

    def listSequence(self):
        params = {}
        for ev in self._events:
            if starts := ev.param("Start Time").compile()[1]:
                params[f"{ev.name()} Start Time"] = starts

            if durs := ev.param("Duration").compile()[1]:
                params[f"{ev.name()} Duration"] = durs

            if odors := ev.param("Odor").compile()[1]:
                params[f"{ev.name()} Odor"] = odors
        return params


OdorEvent = namedtuple("OdorEvent", ["startTime", "duration", "odor"])


class OdorTask(DeviceTask):
    def __init__(self, dev: OdorDelivery, cmd: dict, parentTask):
        """
        cmd: dict
            Structure: {"Event 0 Start Time": start_in_s, "Event 0 Duration": dur_in_s, "Event 0 Odor": (chan, port)}
        """
        super().__init__(dev, cmd, parentTask)
        self._cmd = cmd
        self._events: List[OdorEvent] = []
        i = 0
        while i < len(cmd) / 3:
            self._events.append(
                OdorEvent(cmd[f"Event {i} Start Time"], cmd[f"Event {i} Duration"], cmd[f"Event {i} Odor"])
            )
            i += 1
        self._future = None
        self._result = None

    def configure(self):
        first_chan = self._events[0].odor[0]
        for chan in self.dev.odorChannels():
            self.dev.setChannelValue(chan, 1 if chan == first_chan else 0)

    def isDone(self):
        return self._future is not None and self._future.isDone()

    def getResult(self):
        cmd = self._cmd.copy()
        i = 0
        while odor := cmd.get(f"Event {i} Odor"):
            cmd[f"Event {i} Odor Details"] = self.dev.odorDetails(odor)
            i += 1
        return [cmd]

    def start(self):
        self._future = OdorFuture(self.dev, self._events)

    def stop(self, **kwargs):
        if self._future is not None:
            self._future.stop(reason=kwargs.get("reason"))


class OdorFuture(Future):
    def __init__(self, dev, schedule: List[OdorEvent]):
        super().__init__()
        self._dev = dev
        self._schedule = schedule
        self._duration = max(ev.startTime + ev.duration for ev in schedule)
        self._time_elapsed = 0
        self._thread = threading.Thread(target=self._executeSchedule)
        self._thread.start()

    def percentDone(self):
        if self.isDone():
            return 100
        return 100 * self._time_elapsed / self._duration

    def _executeSchedule(self):
        # TODO this spec is duplicated in the graphing code
        start = datetime.now()
        chan_values = {ev.odor[0]: 0 for ev in self._schedule}
        while True:
            sleep(0.01)
            now = (datetime.now() - start).total_seconds()
            self._time_elapsed = now
            if now > self._duration:  # all done
                for chan in chan_values:
                    self._dev.setChannelValue(chan, 1)
                break
            for event in self._schedule:
                chan, port = event.odor
                action_needed = False
                end_time = event.startTime + event.duration
                if now >= end_time:  # turn off this port after time is up
                    if chan_values[chan] & port > 0:
                        chan_values[chan] ^= port
                        if chan_values[chan] == 0:
                            chan_values[chan] = 1  # ensure at least control is left on
                        action_needed = True
                elif now >= event.startTime:  # time to turn on this port
                    if chan_values[chan] & port == 0:
                        chan_values[chan] &= 0xFE  # Turn off control while other ports are on
                        chan_values[chan] |= port
                        action_needed = True

                if action_needed:
                    self._dev.setChannelValue(chan, chan_values[chan])

        self._isDone = True
