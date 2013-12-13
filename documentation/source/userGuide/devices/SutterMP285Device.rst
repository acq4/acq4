Sutter MP285 Devices
====================

Sutter MP-285 stage and manipulator controllers. NOTE--The MP-285 has a design
flaw: if you turn an attached ROE while the computer is communicating with the
controller, then the controller will crash. This can be circumvented with 
custom interfacing hardware (see lib/drivers/SutterMP285/mp285_hack).



Configuration Options
---------------------

Example configuration:

::
    
    SutterStage:
        driver: 'SutterMP285'
        config:
            port: "COM10"
            baud: 19200
            scale: 1.0, 1.0, 1.0  ## MP285 _should_ report its own scale correctly; 
                                ## no need to adjust it here.
  
Manager Interface
-----------------


Protocol Runner Interface
-------------------------
