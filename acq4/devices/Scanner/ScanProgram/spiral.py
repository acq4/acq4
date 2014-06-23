import numpy as np
import acq4.pyqtgraph as pg
from .component import ScanProgramComponent



class SpiralScanComponent(ScanProgramComponent):
    """
    Scans the laser in the shape of an elliptical spiral.    
    """    
    name = 'spiral'


