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
                 
    def __init__(self, scanProgram=None, cmd=None):
        self.params = None
        self.cmd = cmd
        self.program = weakref.ref(scanProgram)
        self.dt = None

    def isActive(self):
        """
        Return True if this component is currently active.
        """
        return self.ctrlParameter().value()
        
    def ctrlParameter(self):
        """
        The Parameter (see acq4.pyqtgraph.parametertree) set used to allow the 
        user to define this component.        
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
        return self.program.mapToScanner(x, y)

    def generateTask(self):
        """
        Generate the task structure that fully describes the behavior of this 
        component.
        """
        raise NotImplementedError()
        
    @classmethod
    def generateVoltageArray(cls, array, dev, cmd, startInd, stopInd):
        """
        Generate mirror voltages for this scan component and store inside
        *array*. Returns the actual index where this component stopped writing
        values to *array* (must be <= *stopInd*).
        """
        raise NotImplementedError()
        
    def generatePosCmd(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        
        """
        raise NotImplementedError()


    