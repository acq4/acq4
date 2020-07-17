from __future__ import print_function

import threading
from warnings import warn

from acq4.devices.FilterWheel.filterwheel import FilterWheel, FilterWheelFuture, FilterWheelDevGui
from acq4.drivers.zeiss import ZeissMtbSdk
from acq4.util import Qt


class ZeissReflectorChanger(FilterWheel):
    def __init__(self, dm, config, name):
        FilterWheel.__init__(self, dm, config, name)

        self._reflectors = ZeissMtbSdk.getSingleton().getReflectorChanger()
        self._reflectors.registerEventHandlers(onSettle=self._onReflectorPosSettled)
        self._isMoving = False
        self._targetPosition = self.getPosition()
        self._initialSlot = config.pop('initialSlot')

        if self._initialSlot is not None:
            threading.Thread(target=self._setInitialPos).start()  # throwaway so as not to block

    def _onReflectorPosSettled(self, position):
        changes = {'reflector': position}
        self._targetPosition = position
        self.sigFilterChanged.emit(self, changes)
        self._isMoving = False

    def _setInitialPos(self):
        self._setPosition(self._initialSlot)

    def getPositionCount(self):
        return self._reflectors.getElementCount()

    def _getPosition(self):
        # convert 1-based to 0-based index
        return self._reflectors.getPosition() - 1

    def _setPosition(self, newPosition):
        self._isMoving = True

        if self._targetPosition == newPosition:
            self._onReflectorPosSettled(newPosition)
        else:
            # convert 0-based to 1-based index
            self._reflectors.setPosition(newPosition + 1)
        return FilterWheelFuture(self, newPosition)

    def _stop(self):
        warn("`stop` called, but is not implemented for Zeiss Reflector Changers")

    def isMoving(self):
        return self._isMoving

    def deviceInterface(self, win):
        return ZeissFilterChangerDevGui(self)


class ZeissFilterChangerDevGui(FilterWheelDevGui):
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
