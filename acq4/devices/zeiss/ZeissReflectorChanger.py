# Sensapex Seizz SDK Python Wrapper
# All Rights Reserved. Copyright (c) Sensapex Oy 2019
# Author: Ari Salmi
# Version: 0.3

from __future__ import print_function

import threading
import time

from acq4.devices.Device import Device
from acq4.devices.FilterWheel.filterwheel import FilterWheel, FilterWheelFuture, FilterWheelDevGui
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt
from acq4.util.Mutex import Mutex


class ZeissReflectorChanger(FilterWheel):
    def __init__(self, dm, config, name):

        self.reflector = ZeissReflector(dm, config, name)
        self._initialSlot = config.pop('initialSlot')

        FilterWheel.__init__(self, dm, config, name)

        if self._initialSlot is not None:
            initThread = threading.Thread(target=self._setInitialPos)
            initThread.start()

    def _setInitialPos(self):
        # used to wait on the initial home move and then switch to initial slot
        while self.isMoving():
            time.sleep(0.1)

        self._setPosition(self._initialSlot)

    def getPositionCount(self):
        return self.reflector.getPositionCount()

    def _getPosition(self):
        return int(self.reflector.getPosition())

    def _setPosition(self, pos):
        self.reflector.setPosition(pos)
        return ZeissTurretFuture(self, pos)

    def _stop(self):
        self.reflector.stop()

    def isMoving(self):
        return self.reflector.is_moving

    def deviceInterface(self, win):
        return ZeissDevGui(self)

    def quit(self):
        self.stop()


class ZeissTurretFuture(FilterWheelFuture):
    def _atTarget(self):
        if self.dev._getPosition() == self.position:
            return True
        else:
            return FilterWheelFuture._atTarget(self)


class ZeissDevGui(FilterWheelDevGui):
    def __init__(self, dev):
        FilterWheelDevGui.__init__(self, dev)

        self.btnWidget = Qt.QWidget()
        self.layout.addWidget(self.btnWidget, self.layout.rowCount(), 0)

        self.btnLayout = Qt.QGridLayout()
        self.btnWidget.setLayout(self.btnLayout)
        self.btnLayout.setContentsMargins(0, 0, 0, 0)

        self.leftBtn = Qt.QPushButton("<<<")
        self.leftBtn.pressed.connect(self.moveLeft)
        self.btnLayout.addWidget(self.leftBtn, 1, 0)

        self.rightBtn = Qt.QPushButton(">>>")
        self.rightBtn.pressed.connect(self.moveRight)
        self.btnLayout.addWidget(self.rightBtn, 1, 1)

    def moveLeft(self):
        current_pos = self.dev._getPosition()
        if current_pos - 1 >= 0:
            self.dev._setPosition(current_pos - 1)

    def moveRight(self):
        current_pos = self.dev._getPosition()
        if current_pos + 1 < self.dev.getPositionCount():
            self.dev._setPosition(current_pos + 1)


class ZeissReflector(Device):
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(Qt.QMutex.Recursive)

        self.zeiss = ZeissMtbSdk.getSingleton()
        self.mtbRoot = self.zeiss.connect()
        self.m_reflector = self.zeiss.getReflector()
        self.currentIndex = -1
        self.m_reflector.registerEventHandlers(self.onReflectorPosChanged, self.onReflectorPosSettled)
        self.currentIndex = self.m_reflector.getPosition()
        self.is_moving = False
        # print ("Started Zeiss Reflector Changer:" + str(self.currentIndex) )
        # used to emit signal when position passes a threshold

    def onReflectorPosChanged(self, position):
        pass
        # if position != 0:
        #     print ("Reflector change started to: " + str(position-1))

    def onReflectorPosSettled(self, position):
        changes = {'reflector': position - 1}
        # print ("Reflector settled to: " + str(position-1))
        self.currentIndex = position
        self.sigSwitchChanged.emit(self, changes)
        self.is_moving = False

    def quit(self):
        print("Disconnecting Zeiss")
        self.zeiss.disconnect()

    def getPositionCount(self):
        return self.m_reflector.getElementCount()

    def stop(self):
        print("Stopping")
        # Cannot be stopped

    def getPosition(self):
        if self.currentIndex == -1:
            self.currentIndex = self.m_reflector.getPosition()

        if self.currentIndex - 1 < 0:
            return 0

        return self.currentIndex - 1

    def setPosition(self, newPosition):
        self.is_moving = True

        if self.currentIndex != newPosition + 1:
            self.m_reflector.setPosition(newPosition + 1)

        else:
            changes = {'reflector': newPosition}
            self.sigSwitchChanged.emit(self, changes)
            self.is_moving = False
