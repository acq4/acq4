.. _userDevicesWaterSensor:

Water Sensor
============

.. currentmodule:: acq4.devices.WaterSensor

.. autoclass:: WaterSensor
    :members:
    :show-inheritance:

Detects water contact from an analog input channel. Water acts as a ground, so the 60 Hz line noise
on the channel disappears when the sensor is wet.

Configuration
-------------

Example configuration::

    WaterSensor:
        driver: 'WaterSensor'
        channel:
            device: 'NiDAQ'
            channel: '/Dev1/ai0'
            type: 'ai'
            mode: 'nrse'
        method: '60hz_ground'
        interval: 5.0
        threshold: 2.0
        recordDuration: 0.2

* ``channel``: DAQ analog input configuration (required).
* ``method``: only ``'60hz_ground'`` is supported.
* ``interval``: polling interval in seconds (default 5.0).
* ``threshold``: z-score threshold (default 2.0). The z-score compares the summed 3 FFT bins around
  60 Hz (Hann window) with the standard deviation of 6 flanking bins; water is detected when the
  z-score is below the threshold.
* ``recordDuration``: seconds recorded per check (default 0.2).

Features
--------

* Checks once at startup, then periodically in a background thread.
* ``waterDetected(refresh=False)`` returns the last result (True, False, or None if never checked);
  ``refresh=True`` re-runs detection.
* ``sigWaterDetectionChanged(device, waterDetected)`` is emitted when the state changes.
* Device rack widget with a status display and a live signal window.

Dependencies
------------

* A :doc:`DAQ device <NiDAQDevice>` with an analog input
