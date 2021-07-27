from __future__ import print_function

from warnings import warn

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
        self._targetPosition = self._getPosition()
        FilterWheel.__init__(self, dm, config, name)

    def _onPosSettled(self, position):
        self._targetPosition = position
        self.sigFilterChanged.emit(self, position)
        self._isMoving = False

    def _setInitialPos(self):
        self._setPosition(self._initialSlot)

    def getPositionCount(self):
        return self._dev.getElementCount()

    def _getPosition(self):
        # convert 1-based to 0-based index
        return self._dev.getPosition() - 1

    def _setPosition(self, newPosition):
        self._isMoving = True

        if self._targetPosition == newPosition:
            self._onPosSettled(newPosition)
        else:
            # convert 0-based to 1-based index
            self._dev.setPosition(newPosition + 1)
        return FilterWheelFuture(self, newPosition)

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
