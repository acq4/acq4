SensapexObjectiveChanger
========================

.. currentmodule:: acq4.devices.SensapexObjectiveChanger

.. autoclass:: SensapexObjectiveChanger
    :members:
    :show-inheritance:

Motorized Sensapex objective changer with background position polling.

Configuration
-------------

* **deviceId** (int, required): Sensapex device ID of the changer
* **address** (str, optional): network address for the UMP connection
* **group** (int, optional): UMP device group
* **pollInterval** (float, optional): position polling interval in seconds (default 2)

Example configuration::

    ObjectiveChanger:
        driver: 'SensapexObjectiveChanger'
        deviceId: 40
        pollInterval: 1.0

Features
--------

* ``setLensPosition()`` returns a future; the move is retried once after 15 s and then fails
* ``sigSwitchChanged`` emits ``{'lens_position': pos}`` when the position changes
* Switch interface (``setSwitch`` / ``getSwitch``) for the ``lens_position`` switch

Dependencies
------------

* Sensapex UMP driver and hardware
