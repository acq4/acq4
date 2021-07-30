.. _userDevicesSutterMPC200:

Sutter MPC200 motorized stage controller
========================================

This :ref:`Stage device <userDevicesStage>` provides support for Sutter MPC200 stage and manipulator controllers. 


Configuration Options
---------------------

Example configuration:


::
    
    SutterStage:
        driver: 'SutterMPC200'
        port: "COM10"
        drive: 1
        scale: 1.0, 1.0, 1.0  ## If the MPC200 does not report its scale 
                            ## correctly, then corrections may be applied
                            ## here.

Each device represents one drive on the controller; for more drives simply add an additional device configuration and set the drive number accordingly.
