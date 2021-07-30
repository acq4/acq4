.. _userDevicesMockStage:

Simulated stage device
======================

The MockStage device is used to demonstrate and test position tracking functionality in conjunction with a :ref:`MockCamera <userDevicesMockCamera>` device. MockStage implements a simple :ref:`Manager interface <userModulesManagerDevices>` with a virual joystick allowing the stage to be translated.


Configuration Options
---------------------

Example configuration:

::
    
    Stage:
        driver: 'MockStage'
  

