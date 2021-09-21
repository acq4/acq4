.. _userDevicesSutterMP285:

Sutter MP285 Devices
====================

This :ref:`Stage device <userDevicesStage>` provides support for Sutter MP-285 stage and manipulator controllers. 

.. note:: The MP-285 has a design flaw that causes it to crash if an attached ROE is used while the computer is communicating with the controller. This can be circumvented with custom interfacing hardware (see acq4/drivers/SutterMP285/mp285_hack). If possible, it is recommended to use the :ref:`MPC-200 <userDevicesSutterMPC200>` instead.



Configuration Options
---------------------

Example configuration:

::
    
    SutterStage:
        driver: 'SutterMP285'
        port: "COM10"
        baud: 19200
        scale: 1.0, 1.0, 1.0  ## MP285 _should_ report its own scale correctly; 
                            ## no need to adjust it here.
  
