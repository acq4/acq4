"""
Thorlabs MFC1 : microscope focus controller based on Trinamic TMCM-140-42-SE
and PDx-140-42-SE.

"""


"""
Hardware notes:

* Although the controller supports up to 64 microsteps per full step, the
  actual microstep size is not constant and becomes very nonlinear at around 
  16 microsteps. Using mixed_decay_threshold=-1 helps somewhat.

* Stall detection only works for a limited range of current + speed + threshold

* Encoder has 4096 values per rotation; gear ratio is 1:5.

* Setting encoder prescaler to 8192 yields +1 per encoder step 
"""
from .tmcm import TMCM140

class MFC1(object):
    def __init__(self, port, baudrate=9600):
        self.mcm = TMCM140(port, baudrate)
        self.mcm.stop()
        self.mcm.set_params(
            maximum_current=50,
            standby_current=0,
            mixed_decay_threshold=-1,
            encoder_prescaler=8192,
            microstep_resolution=5,
        )
        
    def position(self):
        """Return the current encoder position.
        """
        return self.mcm['encoder_position']
    
    def move(self, position, block=False):
        """Move to the requested position.
        
        If block is False, then return an object that may be used to check 
        whether the move is complete.
        """
        
        
    
    