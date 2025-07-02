Scientifica
===========

.. currentmodule:: acq4.devices.Scientifica

.. autoclass:: Scientifica
    :members:
    :undoc-members:
    :show-inheritance:

The Scientifica device provides support for Scientifica motorized manipulators and stages, including PatchStar, MicroStar, SliceScope, and objective changers.

Configuration
-------------

The device can be configured using either a serial port or device name:

**Connection Options:**
* **port** (str): Serial port (e.g., 'COM1' or '/dev/ttyACM0')
* **name** (str): Device name as assigned in LinLab software

**Communication Settings:**
* **baudrate** (int): Serial baud rate (9600 or 38400, auto-detected if not specified)
* **version** (int): Controller version (default: 2, some devices require version=1)

**Movement Settings:**
* **scale** (tuple): (x, y, z) scale factors in m/step (default: (1e-6, 1e-6, 1e-6))

**Advanced Parameters:**
* **params** (dict): Low-level device parameters including:
  - currents: Motor current limits (**use manufacturer specifications!**)
  - axisScale: Axis scaling factors for coordinate transforms
  - joyDirectionX/Y/Z: Joystick direction settings
  - minSpeed, maxSpeed: Speed limits in device units
  - accel: Acceleration setting
  - joySlowScale, joyFastScale: Joystick speed scaling
  - joyAccel: Joystick acceleration

Example configuration::

    SliceScope:
        driver: 'Scientifica'
        name: 'SliceScope'  # or port: '/dev/ttyACM0'
        baudrate: 38400
        version: 2
        scale: [1e-6, 1e-6, 1e-6]
        params:
            currents: [50, 50, 50]  # Be careful with motor current limits!
            minSpeed: 1
            maxSpeed: 6000
            accel: 100

Supported Devices
-----------------

* **PatchStar**: Patch clamp manipulators
* **MicroStar**: Multi-purpose micromanipulators  
* **SliceScope**: Slice chamber manipulators
* **Objective Changers**: Motorized objective changers
* **Custom Stages**: Other Scientifica motorized devices

Connection Methods
------------------

**By Serial Port:**
Directly specify the serial port for USB/RS232 connections::

    Manipulator:
        driver: 'Scientifica'
        port: '/dev/ttyACM0'  # Linux/Mac
        # or port: 'COM3'     # Windows

**By Device Name:**
Use the name assigned in LinLab software for network connections::

    Manipulator:
        driver: 'Scientifica'
        name: 'MicroStar 2'

Motor Current Warning
---------------------

**CAUTION**: Setting motor currents too high can damage the device. Always follow manufacturer specifications for current limits. Incorrect settings may void warranty or cause permanent damage.

Dependencies
------------

* **Scientifica SDK**: Required for device communication
* **Serial Interface**: USB, RS232, or network connection to Scientifica controller
* **LinLab Software**: For initial device setup and configuration (optional)