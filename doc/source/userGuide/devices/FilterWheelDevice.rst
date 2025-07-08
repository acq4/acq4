FilterWheel
===========

.. currentmodule:: acq4.devices.FilterWheel

.. autoclass:: FilterWheel
    :members:
    :undoc-members:
    :show-inheritance:

The FilterWheel device provides control for motorized filter wheels used in microscopy and imaging systems.

Configuration
-------------

Basic configuration for filter wheel devices includes filter position mapping and communication settings.

Example configuration::

    FilterWheel:
        driver: 'FilterWheel'
        port: '/dev/ttyUSB0'  # Serial port
        filters:
            0: 'Open'
            1: 'DAPI'
            2: 'GFP'
            3: 'Texas Red'
            4: 'Cy5'
            5: 'ND 0.6'

Features
--------

**Filter Management:**
* Named filter positions for easy identification
* Position validation and error checking
* Fast switching between filter positions

**Integration:**
* Task interface for automated filter changes
* Synchronization with imaging sequences
* Coordinate with other optical devices

**Monitoring:**
* Position feedback and status reporting
* Error detection and handling
* Movement completion signaling

Dependencies
------------

* Specific filter wheel hardware and drivers
* Serial or USB communication interface
* Filter wheel controller (if required)