from .FilterWheel.filterwheel import FilterWheel, FilterWheelFuture


class MockFilterWheel(FilterWheel):
    """
    Simulated filter wheel device for testing and demonstration.
    
    Provides the same interface as real filter wheels but without hardware.
    Useful for developing and testing experiments without physical devices.
    
    Configuration options (see FilterWheel base class):
    
    * **filters** (dict): Filter definitions for each position
        - Key: Position number (int)
        - Value: Filter configuration dict with 'name' and optional 'description'
    
    * **parentDevice** (str, optional): Name of parent optical device
    
    * **transform** (dict, optional): Spatial transform relative to parent device
    
    Example configuration::
    
        MockFilterWheel:
            driver: 'MockFilterWheel'
            parentDevice: 'Microscope'
            filters:
                0:
                    name: 'FITC'
                    description: 'Green fluorescence filter'
                1:
                    name: 'Texas Red'
                    description: 'Red fluorescence filter'
                2:
                    name: 'DAPI'
                    description: 'Blue fluorescence filter'
    """
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
