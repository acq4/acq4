PMT (Photomultiplier Tube)
==========================

.. currentmodule:: acq4.devices.PMT

.. autoclass:: PMT
    :members:
    :undoc-members:
    :show-inheritance:

The PMT device provides support for photomultiplier tubes used in light detection applications. It combines DAQ functionality for signal acquisition with optical positioning capabilities.

Configuration
-------------

The PMT device combines DAQGeneric and OptomechDevice features:

* **channels**: DAQ channel definitions for PMT signal and optional plate voltage monitoring
* **parentDevice**: Name of parent optical device (microscope, etc.)
* **transform**: Spatial transform relative to parent device

Example configuration::

    PMT:
        driver: 'PMT'
        parentDevice: 'Microscope'
        channels:
            Input:
                device: 'DAQ'
                channel: '/Dev1/ai0'
                type: 'ai'
            PlateVoltage:
                device: 'DAQ' 
                channel: '/Dev1/ai1'
                type: 'ai'
        transform:
            pos: [0, 0]
            scale: [1, 1]
            angle: 0

The PMT inherits all configuration options from both DAQGeneric (for data acquisition) and OptomechDevice (for optical positioning).