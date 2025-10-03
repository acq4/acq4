PressureControl
===============

.. currentmodule:: acq4.devices.PressureControl

.. autoclass:: PressureControl
    :members:
    :undoc-members:
    :show-inheritance:

The PressureControl device provides control of pressure to a single port, typically used for patch clamp pipette pressure regulation. It may be implemented using a combination of pressure regulators and valves.

Configuration
-------------

Basic configuration options:

* **maximum** (float): Maximum pressure limit in Pascals (default: 50 kPa)
* **minimum** (float): Minimum pressure limit in Pascals (default: -50 kPa)  
* **regulatorSettlingTime** (float): Time to wait for pressure regulator to settle in seconds (default: 0.3)

Example configuration::

    PressureController:
        driver: 'PressureControl'
        maximum: 50000  # 50 kPa
        minimum: -50000 # -50 kPa
        regulatorSettlingTime: 0.3

Features
--------

**Pressure Ramping:**
* Controlled pressure changes over time
* Configurable ramp rates and durations
* Target pressure with tolerance settings

**Pressure Sources:**
* **Regulator**: Controlled pressure from pressure regulator
* **User**: Manual pressure applied by user
* **Atmosphere**: Atmospheric pressure (open to air)

**Safety Features:**
* Pressure limit enforcement
* Automatic settling time management
* Status monitoring and feedback

Usage
-----

**Set Pressure:**
Set immediate pressure to a target value::

    pressureController.setPressure(1000)  # 1 kPa

**Ramp Pressure:**
Gradually change pressure over time::

    # Ramp to 2 kPa over 5 seconds
    pressureController.rampPressure(target=2000, duration=5.0)
    
    # Ramp at 500 Pa/second until reaching 3 kPa
    pressureController.rampPressure(target=3000, rate=500)

**Pressure Sources:**
Switch between pressure sources::

    pressureController.setSource('regulator')  # Use pressure regulator
    pressureController.setSource('atmosphere') # Open to atmosphere
    pressureController.setSource('user')       # Manual user control

Signals
-------

The device emits the following Qt signals:

* **sigBusyChanged**: Emitted when device busy state changes
* **sigPressureChanged**: Emitted when pressure or source changes

Implementation Notes
--------------------

This is a base class that provides the common interface for pressure control devices. Specific implementations should inherit from this class and implement the actual hardware control methods.

Common implementations include:
* DAQ-based pressure control with analog outputs
* Serial/USB pressure controller interfaces
* Sensapex pressure control systems

Dependencies
------------

* Specific hardware driver (depends on implementation)
* Pressure regulator hardware
* Appropriate valve systems for source switching