# -*- coding: utf-8 -*-
from __future__ import print_function

from collections import OrderedDict

from pyqtgraph import SignalBlock

import acq4.util.Mutex as Mutex
from acq4.devices.Device import Device, TaskGui
from acq4.util import Qt


class LightSource(Device):
    """Device tracking the state and properties of a single light-emitting device with one or more internal
    illumination sub-sources.

    Config Options
    --------------
    mock | bool
        Whether to only pretend to be a light source

    All other config options will be treated as the named light source channels (e.g. "blue"). For each of
    these sub-sources, the following options are supported:

    active | bool
        Whether the source should be turned on at the start.
    adjustableBrightness | bool
        Whether or not the device supports setting brightness.
    xkey | tuple
        Configuration for hotkey light source toggle
    """

    # emitted when the on/off/brightness status of a light changes
    sigLightChanged = Qt.Signal(object, object)  # self, light_name

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.sourceConfigs = OrderedDict()  # [name: {'active': bool, 'wavelength': float, 'power': float, ...}, ...]
        self._lock = Mutex.Mutex()
        if config.get("mock", False):
            for key in config:
                if key.lower() in ("driver", "mock"):
                    continue
                self.addSource(key, config[key])

    def deviceInterface(self, win):
        return LightSourceDevGui(self)

    def taskInterface(self, taskRunner):
        return None  # TODO

    def addSource(self, name, conf):
        conf.setdefault("active", False)
        conf.setdefault("adjustableBrightness", False)
        self.sourceConfigs[name] = conf
        if 'xkey' in conf:
            devname, row, col = self.sourceConfigs[name]['xkey']
            dev = self.dm.getDevice(devname)
            dev.addKeyCallback((row, col), self._hotkeyPressed, (name,))

    def describe(self, onlyActive=True):
        """Return a description of the current state of all active light sources.

        If onlyActive is False, then information for all sources will be returned, whether or not they are active.
        """
        if onlyActive:
            return OrderedDict([(n, s) for n, s in self.sourceConfigs.items() if s['active']])
        else:
            return self.sourceConfigs.copy()

    def activeSources(self):
        """Return the names of all active light sources.
        """
        return [s['name'] for s in self.sourceConfigs if s['active']]

    def sourceActive(self, name):
        """Return True if the named light source is currently active.
        """
        return self.sourceConfigs[name]['active']

    def setSourceActive(self, name, active):
        """Activate / deactivate a light source.
        """
        raise NotImplementedError()

    def setSourceActiveFromNamedButton(self, active):
        btn = self.sender()
        self.setSourceActive(btn.objectName(), active)

    def getSourceBrightness(self, name):
        """
        Optional, depending on hardware support.

        Returns
        -------
        float
            A brightness value normalized between 0.0 and 1.0
        """
        raise NotImplementedError()

    def setSourceBrightness(self, name, value):
        """
        Optional, depending on hardware support.

        Parameters
        ----------
        name : str
        value : float
            New brightness setting, normalized between 0.0 and 1.0.
        """
        raise NotImplementedError()

    def _updateXkeyLight(self, name):
        if 'xkey' in self.sourceConfigs[name]:
            devname, row, col = self.sourceConfigs[name]['xkey']
            dev = self.dm.getDevice(devname)
            bl = dev.getBacklights()
            bl[row, col] = int(self.sourceConfigs[name]['active'])
            dev.setBacklights(bl)

    def _hotkeyPressed(self, dev, changes, name):
        self.setSourceActive(name, not self.sourceActive(name))


class LightSourceDevGui(Qt.QWidget):
    def __init__(self, dev):
        """
        Parameters
        ----------
        dev : LightSource
        """
        super(LightSourceDevGui, self).__init__()
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sourceActivationButtons = {}
        self.sourceBrightnessSliders = {}

        for i, name in enumerate(self.dev.sourceConfigs):
            conf = self.dev.sourceConfigs[name]
            if conf.get("adjustableBrightness", False):
                slider = Qt.QSlider()
                slider.setObjectName(name)
                slider_cont = Qt.QGridLayout()
                self.sourceBrightnessSliders[name] = slider
                slider.valueChanged.connect(self._sliderChanged)
                slider_cont.addWidget(slider, 0, 0)
                self.layout.addLayout(slider_cont, 0, i)
            btn = Qt.QPushButton(name)
            btn.setObjectName(name)
            btn.setCheckable(True)
            self.sourceActivationButtons[name] = btn
            self.layout.addWidget(btn, 1, i)
            btn.clicked.connect(self.dev.setSourceActiveFromNamedButton)
        self._updateValuesToMatchDev()
        self.dev.sigLightChanged.connect(self._updateValuesToMatchDev)

    def _sliderChanged(self, value):
        slider = self.sender()
        self.dev.setSourceBrightness(slider.objectName(), value)

    def _updateValuesToMatchDev(self):
        for name in self.dev.sourceConfigs:
            button = self.sourceActivationButtons[name]
            with SignalBlock(button.clicked, self.dev.setSourceActiveFromNamedButton):
                button.setChecked(self.dev.sourceActive(name))
            if name in self.sourceBrightnessSliders:
                slider = self.sourceBrightnessSliders[name]
                with SignalBlock(slider.valueChanged, self._sliderChanged):
                    slider.setValue(int(self.dev.getSourceBrightness(name) * 99))


class LightSourceTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        super(LightSourceTaskGui, self).__init__(dev, taskRunner)
        self.dev = dev
        self.taskRunner = taskRunner
        # TODO?
