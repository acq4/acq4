.. _userDevicesDAQSonicator:

DAQ Sonicator
=============

.. currentmodule:: acq4.devices.DAQSonicator

.. autoclass:: DAQSonicator
    :members:
    :show-inheritance:

A :doc:`Sonicator <SonicatorDevice>` driven through DAQ channels. Protocols are neuroanalysis stimuli
(for example Sine, Chirp, or a Stimulus of several items) evaluated at 1 MHz and output on an analog
channel.

Configuration
-------------

Example configuration::

    Sonicator1:
        driver: 'DAQSonicator'
        capacitance: 65e-9        # optional, farads
        max slew rate: 3.8 * V / µs   # optional
        command:
            device: 'DAQ'
            channel: '/Dev1/ao0'
            type: 'ao'
            scale: 1 / 20         # required: DAQ V / piezo V
        disable:                  # optional
            device: 'DAQ'
            channel: '/Dev1/port0/line0'
            type: 'do'
        overload:                 # optional
            device: 'DAQ'
            channel: '/Dev1/port0/line1'
            type: 'di'
        protocols:
            clean:
                type: "Sine"
                args:
                    start_time: 0
                    duration: 5
                frequency: 150000
                amplitude: 1

Keys read: ``capacitance`` (default 65 nF), ``max current`` (default 0.255 A), ``max slew rate``
(default ``max current / capacitance``), ``command`` (required, must include ``scale``), ``disable``,
``overload``, and ``protocols`` (handled by :class:`Sonicator`).

Features
--------

* Protocol waveform is rejected if its slew rate exceeds the maximum.
* If ``disable`` is configured, the line is set to 0 during output and returned to 1 afterwards
  (holding value is forced to 1).
* If ``overload`` is configured, it is checked before and after output; a set line raises an error.
* ``items`` of a protocol may be written as a dict in the config; it is converted to a list.
* ``calcVoltage(frequency)`` returns the peak voltage allowed by the maximum slew rate.

Dependencies
------------

* A :doc:`DAQ device <NiDAQDevice>` with an analog output (and optional digital lines)
* ``neuroanalysis`` (stimulus definitions)
