import logging
from acq4.pyqtgraph.Qt import QtGui
import falconoptics
from ..FilterWheel.filterwheel import FilterWheel, FilterWheelFuture, FilterWheelDevGui


class FalconTurret(FilterWheel):
    def __init__(self, dm, config, name):
        self.dev = falconoptics.Falcon(config_file=None, update_nonvolatile=True)
        logger = logging.getLogger('falconoptics')
        logger.setLevel(logging.CRITICAL)
        
        if not self.dev.is_homed:
            self.dev.home(block=False)

        FilterWheel.__init__(self, dm, config, name)

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
        self.setPosition('home')
    
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

        self.homeBtn = QtGui.QPushButton("Find Home")
        self.homeBtn.clicked.connect(self.dev.home)

        self.layout.addWidget(self.homeBtn, self.layout.rowCount(), 0)
