Sensapex
========

.. currentmodule:: acq4.devices.Sensapex

.. autoclass:: Sensapex
    :members:
    :undoc-members:
    :show-inheritance:

The Sensapex device provides support for Sensapex micromanipulators and motorized stages through the sensapex-py driver.

Configuration
-------------

Required configuration options:

* **deviceId** (int): Sensapex device ID number
  - < 20 for manipulators
  - >= 20 for stages

Optional configuration:

* **scale** (tuple): (x, y, z) scale factors in meters/step (default: (1e-6, 1e-6, 1e-6))
* **xPitch** (float): Angle of X-axis in degrees relative to horizontal (default: 0)
* **maxError** (float): Maximum movement error tolerance in meters (default: 1e-6)
* **linearMovementRule** (str): Force movement type ("linear", "nonlinear", or None)
* **address** (str): Network address for TCP connection
* **group** (int): Device group number for shared connection
* **nAxes** (int): Number of axes (requires sensapex-py >= 1.22.4)
* **maxAcceleration** (float): Maximum acceleration limit
* **slowSpeed** (float): Slow movement speed in m/s  
* **fastSpeed** (float): Fast movement speed in m/s

Example configuration::

    Manipulator1:
        driver: 'Sensapex'
        deviceId: 1
        scale: [1e-6, 1e-6, 1e-6]
        xPitch: 0
        maxError: 1e-6
        slowSpeed: 5e-6
        fastSpeed: 50e-6
        address: '169.254.255.2'

Device Types
------------

**Manipulators** (deviceId < 20):
- Micromanipulators for precise positioning
- Typically used for patch pipettes, electrodes
- Support for diagonal approach angles

**Stages** (deviceId >= 20):  
- XY stages for sample positioning
- Motorized microscope stages
- Larger range, lower precision than manipulators

Network Configuration
---------------------

Sensapex devices can be connected via:

* **USB**: Direct USB connection to individual devices
* **TCP**: Network connection to Sensapex controller box
* **Shared Connection**: Multiple devices sharing single network connection

For TCP connections, configure the address and group settings. Multiple devices can share a single connection by using the same address and group number.

Movement Types
--------------

The device supports different movement strategies:

* **Linear**: Direct straight-line movements
* **Non-linear**: Multi-step movements to avoid obstacles
* **Automatic**: ACQ4 chooses optimal movement type

Use the `linearMovementRule` parameter to override automatic selection.

Calibration
-----------

The device includes calibration capabilities for:

* Position accuracy verification
* Scale factor calibration
* Coordinate system alignment
* Multi-axis movement validation

Dependencies
------------

* **sensapex-py**: Python driver for Sensapex devices (install via `pip install sensapex`)
* **Compatible Hardware**: Sensapex uMp series manipulators or uMs motorized stages
