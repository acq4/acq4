#  Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c)  Oy 2019
# Author: Ari Salmi
# Version: 0.3
from __future__ import print_function

import time

from acq4.devices.Device import Device
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.util.debug import printExc


class ZeissIllumination(Device):
    sigRLChanged = Qt.Signal(object, object)
    sigTLChanged = Qt.Signal(object, object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.rl_shutter = ZeissRLShutter(dm, config, name + "_rl_shutter")
        self.tl_lamp = ZeissTLLamp(dm, config, name + "tl_lamp")
        # self.rl_shutter.SetRLShutter(2)
        self.rl_shutter.sigSwitchChanged.connect(self.sigRLChanged)
        self.tl_lamp.sigSwitchChanged.connect(self.sigTLChanged)

    def rlChanged(self, position):
        self.sigRLChanged.emit(self, position)

    def tlChanged(self, position):
        self.sigTLChanged.emit(self, position)

    def setRLIllumination(self, state):
        self.rl_shutter.setRLShutter(state)

    def getRLIllumination(self):
        return self.rl_shutter.getRLShutter()

    def setTLIllumination(self, state):
        self.tl_lamp.setTLLamp(state)

    def getTLIllumination(self):
        return self.tl_lamp.getTLLamp()

    def deviceInterface(self, win):
        return ZeissIlluminationGui(self)


class ZeissRLShutter(Device):
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(Qt.QMutex.Recursive)

        self.zeiss = ZeissMtbSdk()
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
        self.zeiss = ZeissMtbSdk()
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
        self.m_tl.setTLLamp(state)

    def getTLLamp(self):
        return self.m_tl.getTLLamp()

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
                pos = self.dev.getTLLamp()
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
        self.tlswitch.clicked.connect(self.tlswitchButtonClicked)

        self.rlswitch = Qt.QPushButton("RL Illumination")
        self.rlswitch.setCheckable(True)
        self.layout.addWidget(self.rlswitch)
        self.rlswitch.clicked.connect(self.rlswitchButtonClicked)

        self.readCurrentPos()

        self.dev.sigRLChanged.connect(self.readCurrentPos)
        self.dev.sigTLChanged.connect(self.readCurrentPos)

    def readCurrentPos(self):
        if self.dev.getTLIllumination() == 1:
            self.tlswitch.setChecked(True)
        else:
            self.tlswitch.setChecked(False)

        if self.dev.getRLIllumination() == 1:
            self.rlswitch.setChecked(False)
        else:
            self.rlswitch.setChecked(True)

    def tlswitchButtonClicked(self):
        if self.dev.getTLIllumination() == 1:
            self.dev.setTLIllumination(2)

        else:
            self.dev.setTLIllumination(1)

    def rlswitchButtonClicked(self):
        if self.dev.getRLIllumination() == 1:
            self.dev.setRLIllumination(2)
        else:
            self.dev.setRLIllumination(1)
