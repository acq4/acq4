.. _userDevicesThorlabsFilterWheel:

Thorlabs Filter Wheel
=====================

.. currentmodule:: acq4.devices.ThorlabsFilterWheel.FilterWheel

.. autoclass:: FilterWheel
    :members:
    :undoc-members:
    :show-inheritance:

Thorlabs FW102C motorized filter wheel over a serial port.

Configuration
-------------

* ``port`` (required): serial port
* ``baud``: default 115200
* ``filters``: dict keyed by slot number, each with ``name`` and ``description``
* ``parentDevice``, ``transform``: as for OptomechDevice

Example configuration::

    FilterWheel:
        driver: 'FilterWheel'
        port: COM4
        baud: 115200
        parentDevice: 'Microscope'
        filters:
            0:
                name: 'green_and_shortpass'
                description: 'ET535/70m Chroma, FESH0700 ThorL'
            1:
                name: 'red'
                description: 'ET630/75m-2p Chroma'

Features
--------

* Position selection and filter lookup
* Speed, trigger mode and sensor mode control
* Task support: a position per task, or a sequence over positions
* Signals for filter, speed, trigger-mode and sensor-mode changes

Dependencies
------------

* ``acq4.drivers.ThorlabsFW102C`` driver and the FW102C hardware
