from __future__ import print_function

import time
from typing import Union
from warnings import warn

from pyqtgraph import ptime

from acq4.devices.FilterWheel.filterwheel import FilterWheel, FilterWheelFuture, FilterWheelDevGui
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt


class ZeissTurret(FilterWheel):
    def __init__(self, dm, config, name):
        zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        if config.get("componentId", "MTBReflectorChanger") == "MTBReflectorChanger":
            self._dev = zeiss.getReflectorChanger()
        else:
            self._dev = zeiss.getObjectiveChanger()
        self._dev.registerEventHandlers(onSettle=self._onPosSettled)
        self._isMoving = False
        FilterWheel.__init__(self, dm, config, name)

    def _onPosSettled(self, position: int):
        print("settled", position)
        self._checkMoveFuture()

    def _setInitialPos(self):
        self._setPosition(self._initialSlot)

    def getPositionCount(self):
        return self._dev.getElementCount()

    def _getPosition(self) -> Union[None, int]:
        position = self._dev.getPosition()
        if position == 0:
            return None
        # convert 1-based to 0-based index
        return position - 1

    def _setPosition(self, newPosition):
        self._isMoving = True

        if self.getPosition() == newPosition:
            fut = ZeissFilterWheelFuture(self, newPosition)
            self._onPosSettled(newPosition + 1)
            return fut
        else:
            # convert 0-based to 1-based index
            self._dev.setPosition(newPosition + 1)
            return ZeissFilterWheelFuture(self, newPosition)

    def _stop(self):
        warn("`stop` called, but is not supported by Zeiss changers")

    def setSpeed(self, speed):
        warn("`setSpeed' not supported on Zeiss changers")

    def getSpeed(self):
        warn("`getSpeed' not supported on Zeiss changers")

    def isMoving(self):
        return self._isMoving

    def deviceInterface(self, win):
        return ZeissTurretDevGui(self)


class ZeissFilterWheelFuture(FilterWheelFuture):
    def isDone(self):
        """Return True if the move has completed or was interrupted.
        """
        if self._wasInterrupted or self._done:
            return True

        if self._atTarget():
            self._done = True
            return True
        else:
            self._wasInterrupted = True
            self._error = f"Filter wheel did not reach target while moving to {self.position} (got to {self.dev.getPosition()})"
            return True

    def _atTarget(self):
        # sometimes we transiently return 0 at the end of a move; just wait a little longer
        start = ptime.time()
        while True:
            pos = self.dev._getPosition()
            if pos != 0 or ptime.time() - start > 1.0:
                break

        return pos == self.position


class ZeissTurretDevGui(FilterWheelDevGui):
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
        self.dev.setPosition((self.dev.getPosition() - 1) % self.dev.getPositionCount())

    def moveRight(self):
        self.dev.setPosition((self.dev.getPosition() + 1) % self.dev.getPositionCount())
