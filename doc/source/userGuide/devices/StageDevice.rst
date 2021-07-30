.. _userDevicesStage:

Movable Stages
==============

ACQ4 supports movable microscope stages and manipulators for both position feedback and position control.
Currently, Sutter MPC200 and MP-285 controllers are supported, and a simulated stage device is available for testing.

Internally, stages are implemented as :ref:`optomechanical devices <userDevicesOptomech>` that introduce a translation into the device hierarchy. The effect of this is that when the position of the stage changes, all devices in the hierarchy attached to the stage are automatically informed of their new position. This allows imaging data to be recorded with its position and orientation relative to the sample, and it allows scanning laser devices to precisely target specific areas of the sample.

Positioning is tracked in 3 dimensions, which allows information about depth to be used on systems with motorized focus or Z-stages. Multiple stages may be connected in the device hierarchy to add their transformations together::
    
    MicroscopeStage:
        driver: 'SutterMPC200'
        port: 'COM10'
        drive: 1
    
    FocusDrive:
        driver: 'SutterMPC200'
        parentDevice: 'MicroscopeStage'
        port: 'COM10'
        drive: 2
    

Stage device subclasses:
    
.. toctree::
    :maxdepth: 1
    
    SutterMP285Device
    SutterMPC200Device
    MockStage
    _SerialMouseDevice


  

.. Manager Interface
.. -----------------

..     .. figure:: images/Stage_ManagerInterface.png


.. Task Runner Interface
.. ---------------------
