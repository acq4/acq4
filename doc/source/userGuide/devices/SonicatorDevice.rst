Sonicator
=========

.. currentmodule:: acq4.devices.Sonicator

.. autoclass:: Sonicator
    :members:
    :undoc-members:
    :show-inheritance:

The Sonicator device provides control for ultrasonic cleaning devices, typically used for cleaning patch pipette tips during automated patching procedures.

Configuration
-------------

Basic configuration for sonicator control:

Example configuration::

    Sonicator:
        driver: 'Sonicator'
        # Implementation-specific settings would go here

Features
--------

**Ultrasonic Cleaning:**
* Controlled activation of ultrasonic cleaning
* Configurable cleaning duration and intensity
* Safety interlocks and monitoring

**Integration with Patching:**
* Coordination with patch pipette devices
* Automated cleaning sequences
* State management during cleaning cycles

**Safety Features:**
* Timeout protection
* Status monitoring
* Error handling and recovery

Usage
-----

The sonicator is typically used as part of automated patching workflows to clean pipette tips when they become fouled or blocked.

Dependencies
------------

* Ultrasonic cleaning hardware
* Appropriate control interface (DAQ, serial, etc.)
* Safety interlocks and monitoring systems