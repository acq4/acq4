#  Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c)  Oy 2019
# Author: Ari Salmi
# Version: 0.3
from __future__ import print_function

import time

from acq4.devices.Device import Device
from acq4.devices.LightSource import LightSource
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.util.debug import printExc


class ZeissLamp(LightSource):
    TRANSMISSIVE = "Transmissive"
    REFLECTIVE = "Reflective"

    sigActiveChanged = Qt.Signal(object, object)

    def __init__(self, dm, config, name):
        LightSource.__init__(self, dm, config, name)
        self._zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config["transOrReflect"] == ZeissLamp.TRANSMISSIVE:
            self._lamp = self._zeiss.getTLLamp()
        else:
            self._lamp = self._zeiss.getRLLamp()
        self.addSource("default", config)

    def setSourceActive(self, name, active):
        self._lamp.setIsActive(active)
        self._sources["default"]["active"] = active


class ZeissRLShutter(Device):
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(Qt.QMutex.Recursive)

        self.zeiss = ZeissMtbSdk.getSingleton()
        self.mtbRoot = self.zeiss.connect()
        self.m_shutter = self.zeiss.getShutter()
        self.zeiss.getShutter().registerEvents(self.shutterStateChanged, self.shutterStateSettled)
        self.zeiss.getShutter().registerRLShutterEvents(self.rlShutterStateChanged)

    def shutterStateChanged(self, position):
        pass

    def shutterStateSettled(self, position):
        self.sigSwitchChanged.emit(self, position)

    def rlShutterStateChanged(self, position):
        pass

    def setRLShutter(self, state):
        self.m_shutter.setRLShutter(state)

    def getRLShutter(self):
        return self.m_shutter.getRLShutter()

    def disconnect(self):
        self.zeiss.disconnect()


class ZeissTLLamp(Device):
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.zeiss = ZeissMtbSdk.getSingleton()
        self.mtbRoot = self.zeiss.connect()
        self.m_tl = self.zeiss.getTLLamp()
        self.m_tl.registerEvents(self.tlStateChanged, self.tlStateSettled)
        self.readThread = TLLampPollThread(self, interval=1.0)
        self.readThread.start()

    def tlStateChanged(self, position):
        pass

    def tlStateSettled(self, position):
        self.sigSwitchChanged.emit(self, position)

    def setTLLamp(self, state):
        self.m_tl.setIsActive(state)

    def _getIsActive(self):
        return self.m_tl.getIsActive()

    def disconnect(self):
        self.zeiss.disconnect()


class TLLampPollThread(Thread):
    def __init__(self, dev, interval=1.0):
        Thread.__init__(self)
        self.dev = dev
        self.interval = interval

    def run(self):
        self.stopThread = False
        pos = -1
        while self.stopThread is False:
            try:
                prev_pos = pos
                pos = self.dev.getIsActive()
                if pos != prev_pos:
                    self.dev.tlStateSettled(pos)

                time.sleep(self.interval)
            except:
                printExc("Error in TL Lamp poll thread")
                time.sleep(1.0)

    def stop(self):
        self.stopThread = True


class ZeissIlluminationGui(Qt.QWidget):
    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.layout.setContentsMargins(0, 0, 0, 0)

        self.tlswitch = Qt.QPushButton("TL Illumination")
        self.tlswitch.setCheckable(True)
        self.layout.addWidget(self.tlswitch)
        self.tlswitch.clicked.connect(self._tlSwitchButtonClicked)

        self.rlswitch = Qt.QPushButton("RL Illumination")
        self.rlswitch.setCheckable(True)
        self.layout.addWidget(self.rlswitch)
        self.rlswitch.clicked.connect(self._rlSwitchButtonClicked)

        self._readCurrentPos()

        self.dev.sigRLChanged.connect(self._readCurrentPos)
        self.dev.sigTLChanged.connect(self._readCurrentPos)

    def _readCurrentPos(self):
        if self.dev.getTLIllumination():
            self.tlswitch.setChecked(True)
        else:
            self.tlswitch.setChecked(False)

        if self.dev.getRLIllumination():
            self.rlswitch.setChecked(False)
        else:
            self.rlswitch.setChecked(True)

    def _tlSwitchButtonClicked(self):
        self.dev.setTLIllumination(not self.dev.getTLIllumination())

    def _rlSwitchButtonClicked(self):
        self.dev.setRLActive(not self.dev.getRLIllumination())
