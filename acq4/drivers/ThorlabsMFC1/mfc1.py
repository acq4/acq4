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
        self.mcm.stop_program()
        self.mcm.stop()
        self.mcm.set_params(
            maximum_current=50,
            maximum_acceleration=1000,
            maximum_speed=2000,
            ramp_divisor=7,
            pulse_divisor=3,
            standby_current=0,
            mixed_decay_threshold=-1,
            encoder_prescaler=8192,
            microstep_resolution=5,
            fullstep_threshold=0,
            stall_detection_threshold=0,
        )
        self.mcm.set_global('gp0', self.mcm['encoder_position'])
        self._upload_program()
        
    def _upload_program(self):
        """Upload a program used to seek to a specific encoder value.
        """
        m = self.mcm
        with m.write_program() as p:
            # start with a brief wait because sometimes the first command may be 
            # ignored.
            p.command('wait', 0, 0, 1)

            # distance = target_position - current_position
            p.get_param('encoder_position')
            p.calcx('load')
            p.get_global('gp0')
            p.calcx('sub')
            p.set_global('gp1', 'accum')
            
            # if dx is 0, stop motor and program
            p.comp(0)
            p.jump('ne', p.count+3)
            p.set_param('target_speed', 0)
            p.set_param('actual_speed', 0)
            p.command('stop', 0, 0, 0)
            
            # calculate distance-to-target where we should begin (de)acccelerating
            # Tx = speed**2 / 1572 
            p.get_param('actual_speed')
            p.calcx('load')
            p.calcx('mul')
            p.calc('div', 1400)
            
            p.calcx('swap')  # invert threshold if v < 0
            p.get_param('actual_speed')
            p.comp(0)
            p.calcx('swap')
            p.jump('ge', p.count+1)
            p.calc('mul', -1)    
            p.set_global('gp2', 'accum')
            
            # calculate desired speed
            p.calcx('swap')
            p.get_global('gp1')
            p.calcx('sub')
            p.calcx('swap')
            p.get_param('actual_speed')
            p.calcx('add')
            p.calc('mul', 2)
            p.calc('div', 3)
            
            # new_speed = clip(new_speed, -2047, 2047)
            max = 2000
            p.comp(max)
            p.jump('gt', p.count+3)
            p.comp(-max)
            p.jump('lt', p.count+3)
            p.jump(p.count+3)
            p.calc('load', max)
            p.jump(p.count+1)
            p.calc('load', -max)
            
            # 0 speed should never be requested if there is an offset
            p.comp(0)
            p.jump('ne', p.count+1)
            p.get_global('gp1')
            
            
            # output and repeat
            p.set_param('target_speed', 'accum')
            #p.set_param('actual_speed', 'accum')
            p.jump(1)

    def position(self):
        """Return the current encoder position.
        """
        return self.mcm['encoder_position']
    
    def move(self, position, block=False):
        """Move to the requested position.
        
        If block is False, then return an object that may be used to check 
        whether the move is complete.
        """
        self.mcm.set_global('gp0', position)
        self.mcm.start_program()
        
    def rotate(self, speed):
        """Begin rotating at *speed*. Positive values turn right.
        """
        self.mcm.stop_program()
        self.mcm.rotate(speed)
    
    def stop(self):
        """Immediately stop the motor and any programs running on the motor
        comtrol module.
        """
        self.mcm.stop_program()
        self.mcm.stop()
