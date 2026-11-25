.. _userDevicesCoolLEDLightSource:

CoolLED Light Source
====================

.. currentmodule:: acq4.devices.CoolLEDLightSource

.. autoclass:: CoolLEDLightSource
    :members:
    :undoc-members:
    :show-inheritance:

CoolLED LED light source controlled over a serial connection (57600 baud).

Configuration
-------------

* ``port`` (required): serial port, or ``'probe'`` to scan ports for a CoolLED device (probing talks to other serial ports)

Three sources, ``A``, ``B`` and ``C``, are created automatically, all with adjustable brightness.
``parentDevice`` and ``transform`` are inherited from LightSource.

Example configuration::

    CoolLED:
        driver: 'CoolLEDLightSource'
        port: 'COM3'
        parentDevice: 'Microscope'

Features
--------

* Per-channel on/off and brightness commands, queued and sent by a background I/O thread
* Channel state and brightness parsed from device status responses

Dependencies
------------

* ``acq4.drivers.SerialDevice`` and the CoolLED USB serial driver
