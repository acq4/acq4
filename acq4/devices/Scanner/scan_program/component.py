from __future__ import print_function
from acq4.util import Qt
import weakref


class ScanProgramComponent(object):
    """
    Base class for all components that make up a scan program.
    
    Provides the following services:
    
    * Simple GUI for generating task command
    * Draws interactive representation of command in camera module
    * Convert task command to mirror voltage command
    * Save / restore functionality
    * Masking arrays for controlling laser power
    * Extraction and analysis of imaging data generated during a scan
    
    """
    
    type = None  # String identifying the type of this scan component.
                 
    def __init__(self, scanProgram):
        self._laser = None
        self.params = None
        self.program = weakref.ref(scanProgram)

    @property
    def name(self):
        """Return the name of this component.
        """
        return self.ctrlParameter().name()
    
    def setLaser(self, laser):
        self._laser = laser

    @property
    def laser(self):
        if self._laser is None:
            return self.program().laser
        else:
            return self._laser

    def samplingChanged(self):
        """Called by parent ScanProgram when any sampling parameters have
        changed.
        """
        pass
        
    def isActive(self):
        """Return True if this component is currently active.
        """
        return self.ctrlParameter().value()
        
    def ctrlParameter(self):
        """
        The Parameter set (see acq4.pyqtgraph.parametertree) that allows the 
        user to configure this component.
        """
        raise NotImplementedError()
    
    def graphicsItems(self):
        """
        A list of GraphicsItems to be displayed in a camera module or image
        analysis module. These show the location and shape of the scan 
        component, and optionally offer user interactivity to define the shape.
        """
        raise NotImplementedError()

    def mapToScanner(self, x, y):
        """Map from global coordinates to scan mirror voltages, using the
        ScanProgram to provide the mapping.
        """
        return self.program().scanner.mapToScanner(x, y, self.laser.name())

    def generateVoltageArray(self, array):
        """Generate mirror voltages for this scan component and store inside
        *array*. Returns the start and stop indexes used by this component.
        """
        raise NotImplementedError()
        
    def generatePosArray(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        """
        raise NotImplementedError()

    def scanMask(self):
        """Return a boolean array indicating regions where this component 
        drives the scan mirrors.
        """
        raise NotImplementedError()

    def laserMask(self):
        """Return boolean array indicating regions where this component intends
        the laser to be active. 
        
        By default, this returns the output of scanMask().
        """
        return self.scanMask()

    def saveState(self):
        """Return a serializable data structure representing the state of this 
        component.
        
        Subclasses must extend this method.
        """
        state = {'type': self.type}
        return state
    
    def restoreState(self, state):
        """Restore the state of this component from the result of a previous 
        call to saveState(). 
        """
        raise NotImplementedError()

    def updateVisibility(self):
        """
        """
        v = self.program().isVisible() and self.isActive()
        for item in self.graphicsItems():
            item.setVisible(v)
