from .FilterWheel.filterwheel import FilterWheel, FilterWheelFuture


class MockFilterWheel(FilterWheel):
    def __init__(self, dm, config, name):
        self._position = 0
        FilterWheel.__init__(self, dm, config, name)

    def _setPosition(self, pos):
        assert pos in self._filters, "Unknown filter wheel position %r" % pos
        self._position = pos
        return FilterWheelFuture(self, pos)

    def _getPosition(self):
        return self._position

    def isMoving(self):
        return False

    def _stop(self):
        pass

    def setSpeed(self, speed):
        pass
    
    def getSpeed(self):
        pass
