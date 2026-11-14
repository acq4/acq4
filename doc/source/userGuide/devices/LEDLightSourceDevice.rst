.. _userDevicesLEDLightSource:

LED Light Source (DAQ)
======================

.. currentmodule:: acq4.devices.LEDLightSource.LEDLightSource

.. autoclass:: LEDLightSource
    :members:
    :undoc-members:
    :show-inheritance:

Light sources switched by DAQ output channels, with a configurable "on" value per source.

Configuration
-------------

``sources`` (or ``leds``) maps each source name to:

* ``channel``: ``[device_name, channel]`` of the DAQ output (required)
* ``onValue``: output value when on (default 1.0)
* ``wavelength``: wavelength in meters (optional)
* ``adjustableBrightness``: default False

``parentDevice`` and ``transform`` are inherited from LightSource.

Example configuration::

    LEDArray:
        driver: 'LEDLightSource'
        parentDevice: 'Microscope'
        sources:
            Blue:
                channel: ['DAQ', '/Dev1/port0/line0']
                wavelength: 470e-9
                onValue: 5.0

Features
--------

* Turns a source on or off by setting the channel holding value to ``onValue`` or 0
* Tracks external holding-value changes on the DAQ device and emits ``sigLightChanged``

Dependencies
------------

* A DAQ device exposing ``setChanHolding``, ``getChanHolding`` and ``sigHoldingChanged``
