

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
    
    def __init__(self, cmd, generator):
        self.cmd = cmd
        self.gen = generator
        self.dt = None
        
    def mapToScanner(self, x, y):
        return self.gen.mapToScanner(x, y)
        
    def generateVoltageArray(self, array, startInd, stopInd):
        """
        Generate mirror voltages for this scan component and store inside
        *array*. Returns the *last* index actually used (this must be less
        than *stopInd*).
        """
        raise NotImplementedError()
        
    def generatePosCmd(self, array):
        """
        Generate the position commands for this scan component and store
        inside *array*.
        
        """
        raise NotImplementedError()


