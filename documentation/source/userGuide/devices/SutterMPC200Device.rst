Sutter MPC200 motorized stage controller
========================================

Sutter MPC200


Configuration Options
---------------------

Example configuration:


::
    
    SutterStage:
        driver: 'SutterMPC200'
        config:
            port: "COM10"
            drive: 1
            scale: 1.0, 1.0, 1.0  ## If the MPC200 does not report its scale 
                                ## correctly, then corrections may be applied
                                ## here.

Each device represents one drive on the controller; for more drives simply add a new device and set the drive number accordingly.


Manager Interface
-----------------


Protocol Runner Interface
-------------------------
