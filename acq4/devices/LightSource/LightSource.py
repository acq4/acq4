# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.devices.Device import Device, TaskGui
from acq4.util import Qt
import acq4.util.Mutex as Mutex
from collections import OrderedDict


class LightSource(Device):
    """Device tracking the state and properties of a single light-emitting device with one or more internal
    illumination sources.
    """

    # emitted when the on/off status of a light changes
    sigLightChanged = Qt.Signal(object, object)  # self, light_name

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.sourceConfigs = OrderedDict()  # [name: {'active': bool, 'wavelength': float, 'power': float, ...}, ...]
        self._lock = Mutex.Mutex()

    def deviceInterface(self, win):
        return LightSourceGui(self)

    def taskInterface(self, taskRunner):
        return LightSourceTaskGui(self, taskRunner)

    def addSource(self, name, conf):
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


class LightSourceGui(Qt.QWidget):
    def __init__(self, dev):
        """
        Parameters
        ----------
        dev : LightSource
        """
        super(LightSourceGui, self).__init__()
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sourceActivationButtons = {}
        self.sourceBrightnessSliders = {}
        for i, name in enumerate(self.dev.sourceConfigs):
            src = self.dev.sourceConfigs[name]
            if src.get("adjustableBrightness", False):
                slider = Qt.QSlider()
                slider_cont = Qt.QGridLayout()
                self.sourceBrightnessSliders[name] = slider
                slider.valueChanged.connect(lambda val: self.dev.setSourceBrightness(name, val / 99.))  # 0-99
                slider_cont.addWidget(slider, 0, 0)
                self.layout.addLayout(slider_cont, 0, i)
            btn = Qt.QPushButton(name)
            btn.setCheckable(True)
            self.sourceActivationButtons[name] = btn
            self.layout.addWidget(btn, 1, i)
            btn.clicked.connect(lambda isOn: self.dev.setSourceActive(name, isOn))
        # TODO get initial values
        # TODO hook into device changes
        # TODO test that device changes don't mess with user


class LightSourceTaskGui(TaskGui):
    def __init__(self, dev, taskRunner):
        super(LightSourceTaskGui, self).__init__(dev, taskRunner)
        self.dev = dev
        self.taskRunner = taskRunner
        # TODO