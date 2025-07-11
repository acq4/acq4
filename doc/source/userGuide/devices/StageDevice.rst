.. _userDevicesStage:

Movable Stages
==============

ACQ4 supports movable microscope stages and manipulators for both position feedback and position control.
Supported devices include Scientifica, Sensapex, Sutter, MicroManager-compatible stages, New Scale Technologies, Thorlabs, and simulated devices for testing.

Internally, stages are implemented as :ref:`optomechanical devices <userDevicesOptomech>` that introduce a translation into the device hierarchy. The effect of this is that when the position of the stage changes, all devices in the hierarchy attached to the stage are automatically informed of their new position. This allows imaging data to be recorded with its position and orientation relative to the sample, and it allows scanning laser devices to precisely target specific areas of the sample.

Positioning is tracked in 3 dimensions, which allows information about depth to be used on systems with motorized focus or Z-stages. Multiple stages may be connected in the device hierarchy to add their transformations together::
    
    MicroscopeStage:
        driver: 'Scientifica'
        name: 'SliceScope'
        scale: [-1e-6, -1e-6, 1e-6]
    
    FocusDrive:
        driver: 'ThorlabsMFC1'
        parentDevice: 'MicroscopeStage'
        port: 'COM9'
        scale: [1.0, 1.0, 1e-6]
    

Supported Hardware
    
* :doc:`ScientificaDevice` - PatchStar, MicroStar, SliceScope manipulators and stages with objective changer support
* :doc:`SensapexDevice` - uMp micromanipulators and uMs motorized stages
* :doc:`MicroManagerStageDevice` - Generic interface for Micro-Manager compatible stage hardware
* :doc:`NewScaleMPMDevice` - New Scale Technologies MPM piezoelectric positioning modules with network control
* :doc:`ThorlabsMFC1Device` - Thorlabs MFC1 motorized focus controller for Z-axis control
* :doc:`MockStage` - Simulated stage device for testing and development
* :doc:`_SerialMouseDevice` - Serial mouse input device for manual stage control (currently not maintained)
* :doc:`SutterMP285Device` - Single micromanipulator with serial communication (currently not maintained)
* :doc:`SutterMPC200Device` - Multi-channel controller supporting up to 4 drives (currently not maintained)
  

.. Manager Interface
.. -----------------

..     .. figure:: images/Stage_ManagerInterface.png


.. Task Runner Interface
.. ---------------------
