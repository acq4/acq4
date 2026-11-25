.. _userDevicesSensapexPressureControl:

Sensapex Pressure Control
=========================

.. currentmodule:: acq4.devices.SensapexPressureControl

.. autoclass:: SensapexPressureControl
    :members:
    :undoc-members:
    :show-inheritance:

Pressure controller using a Sensapex pressure channel. The ``user`` and ``atmosphere`` sources share one valve state.

Configuration
-------------

* ``deviceId`` (required): Sensapex device ID
* ``pressureChannel`` (required): pressure channel number
* ``address``, ``group``: UMP connection (optional; otherwise the ``drivers/sensapex`` global config)
* ``pollInterval``: seconds between measurements (default 1)
* ``maximum`` / ``minimum``: pressure limits in Pa (defaults 70000 / -70000)
* ``regulatorSettlingTime``: inherited from PressureControl

Example configuration::

    SensapexPressure:
        driver: 'SensapexPressureControl'
        deviceId: 30
        pressureChannel: 1
        pollInterval: 0.5

Features
--------

* Sources: ``regulator``, ``atmosphere``, ``user``
* Background polling of measured pressure (``sigMeasuredPressureChanged``) and busy status (``sigBusyChanged``)
* ``calibrate()`` for the pressure sensor; the GUI calibrate button is disabled while the device is busy
* Device GUI showing measured pressure

Dependencies
------------

* ``acq4.drivers.sensapex`` and a Sensapex pressure unit
