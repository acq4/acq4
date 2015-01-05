from PyQt4 import QtGui, QtCore
import weakref


class ScanProgramComponent:
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
    
    name = None  # Must be the string used to identify this component
                 # in the task command structure.
                 
    def __init__(self, scanProgram):
        self._laser = None
        self.params = None
        self.program = weakref.ref(scanProgram)

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

    def generateTask(self):
        """
        Generate the task structure that fully describes the behavior of this 
        component.
        """
        raise NotImplementedError()
        
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
