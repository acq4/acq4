.. _userDevicesAccesOdorDelivery:

ACCES Odor Delivery
===================

.. currentmodule:: acq4.devices.AccesOdorDelivery

.. autoclass:: AccesOdorDelivery
    :members:
    :show-inheritance:

An odor delivery device that switches valves through the digital outputs of an ACCES I/O USB-DIO-96.

Configuration
-------------

Example configuration::

    OdorDelivery:
        driver: 'AccesOdorDelivery'
        deviceId: 0
        triggerReadChannel: 11
        odors:
            banana: 0
            apple: 1
            vanilla: 2

* ``deviceId`` (optional): USB-DIO-96 device ID; defaults to the single-device default.
* ``triggerReadChannel`` (optional, default 11)
* ``odors``: odor name to digital output channel, as for the OdorDelivery base class.

Features
--------

* Every channel listed in ``odors`` is configured as a digital output.
* ``setChannelValue(channel, value)`` writes to the corresponding output line.

Dependencies
------------

* ACCES I/O USB-DIO-96 and its driver (``acq4.drivers.Acces.UsbDIO96``)
