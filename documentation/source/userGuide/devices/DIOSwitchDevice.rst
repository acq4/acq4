Digital Switch 
==============

This device polls a DAQ digital input port and is used to notify the system that the state of the port has changed. Currently this is used by the Microscope device to determine when its objective lens has changed.

Configuration Options
---------------------

Example configuration:

::
    
    Switch:    
        driver: 'DIOSwitch'
        config:
            channels: 
                objective:
                    device: 'DAQ'
                    channel: '/Dev1/line12'  ## indicates the state of the objective switch
                PMT:
                    device: 'DAQ'
                    channel: '/Dev1/line6'   ## detects when PMT aperture is open
            interval: 300e-3  ## poll for changes every 300ms


Manager Interface
-----------------


Protocol Runner Interface
-------------------------
