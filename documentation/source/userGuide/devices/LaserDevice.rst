Lasers
======

Lasers are used in ACQ4 for photostimulation and scanning laser imaging, usually in conjuction with a Scanner device.
Lasers provide:
   
* Calibrated output through a variety of mechanisms:
    * Q-switch or shutter-controlled pulses
    * Pockel cell attenuation
    * Pulse-width modulation
* Output calibration accounts for attenuation factors which are dependent on optical pathway (for example, each objective lens may have a different attenuation factor).
    

Configuration Options
---------------------

Example configuration:

::
    
    Laser-UV:
        driver: 'Laser'
        config:
            parentDevice: 'Microscope'
            pulseRate: 100*kHz                      ## Laser's pulse rate
            power: 100*mW
            shutter:
                device: 'DAQ'
                channel: '/Dev1/line30'           ## channel for triggering shutter
                type: 'do'
                delay: 10*ms                      ## how long it takes the shutter to fully open
            wavelength: 355*nm
            alignmentMode:
                shutter: True
            defaultPowerMeter: 'NewportMeter'
  
  

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
