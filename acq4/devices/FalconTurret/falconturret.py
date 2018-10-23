import logging, threading, time
from acq4.util import Qt
import falconoptics
from ..FilterWheel.filterwheel import FilterWheel, FilterWheelFuture, FilterWheelDevGui


class FalconTurret(FilterWheel):
    def __init__(self, dm, config, name):
        self.dev = falconoptics.Falcon(config_file=None, update_nonvolatile=True)
        logger = logging.getLogger('falconoptics')
        logger.setLevel(logging.CRITICAL)

        # can't go to initial until home completes.
        self._initialSlot = config.pop('initialSlot')

        FilterWheel.__init__(self, dm, config, name)

        if not self.dev.is_homed:
            self._initialFuture = self.home()

        if self._initialSlot is not None:
            initThread = threading.Thread(target=self._setInitialPos)
            initThread.start()

    def _setInitialPos(self):
        # used to wait on the initial home move and then switch to initial slot
        while not self._initialFuture.isDone():
            time.sleep(0.1)
        self.setPosition(self._initialSlot)

    def getPositionCount(self):
        return self.dev._total_slides

    def _getPosition(self):
        return int(self.dev.current_slide) % self.dev._total_slides

    def _setPosition(self, pos):
        if pos == 'home':
            self.dev.home(block=False)
        else:
            self.dev.move_to_slide(pos, block=False)
        return FalconTurretFuture(self, pos)

    def home(self):
        """Search for home position on turret; used to recalibrate wheel location.
        """
        return self.setPosition('home')
    
    def _stop(self):
        self.dev.emergency_stop()

    def isMoving(self):
        return self.dev.is_moving

    def deviceInterface(self, win):
        return FalconDevGui(self)

    def quit(self):
        self.stop()

    
class FalconTurretFuture(FilterWheelFuture):
    def _atTarget(self):
        if self.position == 'home':
            return self.dev.dev.is_homed
        else:
            return FilterWheelFuture._atTarget(self)


class FalconDevGui(FilterWheelDevGui):
    def __init__(self, dev):
        FilterWheelDevGui.__init__(self, dev)

        self.btnWidget = Qt.QWidget()
        self.layout.addWidget(self.btnWidget, self.layout.rowCount(), 0)

        self.btnLayout = Qt.QGridLayout()
        self.btnWidget.setLayout(self.btnLayout)
        self.btnLayout.setContentsMargins(0, 0, 0, 0)

        self.homeBtn = Qt.QPushButton("Find Home")
        self.homeBtn.clicked.connect(self.dev.home)
        self.btnLayout.addWidget(self.homeBtn, 0, 0, 1, 2)

        self.leftBtn = Qt.QPushButton("<<<")
        self.leftBtn.pressed.connect(self.moveLeft)
        self.leftBtn.released.connect(self.stop)
        self.btnLayout.addWidget(self.leftBtn, 1, 0)

        self.rightBtn = Qt.QPushButton(">>>")
        self.rightBtn.pressed.connect(self.moveRight)
        self.rightBtn.released.connect(self.stop)
        self.btnLayout.addWidget(self.rightBtn, 1, 1)

    # Manual turret rotation is hacky but only meant for diagnosing
    # filter position issues; normal operation should not need this.
    def moveLeft(self):
        self.dev.dev._motor_on()
        self.dev.dev._target_velocity = -self.dev.dev._home_speed

    def moveRight(self):
        self.dev.dev._motor_on()
        self.dev.dev._target_velocity = self.dev.dev._home_speed

    def stop(self):
        self.dev.dev._target_velocity = 0
        self.dev.dev._motor_off()
