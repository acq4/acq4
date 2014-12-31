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
        self.sampleRate = 1000
        self.downsample = 1
        self.program = weakref.ref(scanProgram)

    def setSampleRate(self, rate, downsample):
        self.sampleRate = rate
        self.downsample = downsample

    def isActive(self):
        """
        Return True if this component is currently active.
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
        return self.program.mapToScanner(x, y)

    def generateTask(self):
        """
        Generate the task structure that fully describes the behavior of this 
        component.
        """
        raise NotImplementedError()
        
    @classmethod
    def generateVoltageArray(cls, array, dev, cmd):
        """
        Generate mirror voltages for this scan component and store inside
        *array*. Returns the start and stop indexes used by this component.
        """
        raise NotImplementedError()
        
    def generatePosCmd(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        
        """
        raise NotImplementedError()



class ComponentScanGenerator(object):
    """Class responsible for computing and saving information about the geometry
    of the scan.
    """
    def writeArray(self, array, mapping=None):
        """
        Given a (N,2) array, write the scan path into the 
        array region(s) used by this component.
        
        The optional *mapping* argument provides a callable that maps from 
        global position to another coordinate system (eg. mirror voltage).
        It must accept two arrays as arguments: (x, y)
        """

    def writeMask(self, array):
        """
        Write 1s into the array in the active region of the scan.
        This is used to indicate the part of the scan when the laser should be enabled. 
        """
        offset = self.activeOffset
        shape = self.activeShape
        stride = self.activeStride
        
        target = pg.subArray(array, offset, shape, stride)
        target[:] = 1


