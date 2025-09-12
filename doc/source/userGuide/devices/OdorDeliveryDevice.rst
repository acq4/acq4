OdorDelivery
============

.. currentmodule:: acq4.devices.OdorDelivery

.. autoclass:: OdorDelivery
    :members:
    :undoc-members:
    :show-inheritance:

The OdorDelivery device provides control for valve-based odor delivery systems used in olfactory research and behavioral experiments.

Configuration
-------------

The device is configured with a mapping of odor channels and ports:

* **odors** (dict): Odor channel and port definitions
  - Key: Channel group name (arbitrary string)
  - Value: Channel configuration dict containing:
    - **channel** (int): Hardware channel number
    - **ports** (dict): Port number to odor name mapping

Example configuration::

    OdorDelivery:
        driver: 'OdorDelivery'
        odors:
            'Group A':
                channel: 0
                ports:
                    2: 'Ethyl Butyrate'
                    4: 'Citral'
                    6: 'Vanilla'
                    8: 'Mineral Oil'
            'Group B':
                channel: 1
                ports:
                    2: 'Isoamyl Acetate'
                    4: 'Geraniol'
                    6: 'Blank'

Features
--------

**Multi-Channel Support:**
* Multiple independent odor delivery channels
* Each channel can have multiple odor ports
* Flexible port-to-odor mapping

**Valve Control:**
* Precise timing control for odor delivery
* Support for multiple valve types
* Coordinated multi-valve operations

**Stimulus Generation:**
* Integration with ACQ4's stimulus generation system
* Programmable odor delivery sequences
* Synchronized delivery with other experimental events

**Task Interface:**
* GUI interface for interactive odor delivery
* Parameter trees for stimulus configuration
* Real-time control and monitoring

Usage Examples
--------------

**Simple Odor Delivery:**
Deliver a specific odor for a defined duration::

    # Deliver 'Citral' from Group A for 2 seconds
    odorDevice.deliverOdor('Group A', 'Citral', duration=2.0)

**Sequence Programming:**
Create complex odor delivery sequences::

    sequence = [
        {'channel': 'Group A', 'odor': 'Ethyl Butyrate', 'duration': 1.0, 'delay': 0.5},
        {'channel': 'Group B', 'odor': 'Isoamyl Acetate', 'duration': 1.5, 'delay': 1.0},
    ]
    odorDevice.runSequence(sequence)

Task Integration
----------------

The OdorDelivery device provides TaskGui integration for use in experimental protocols:

* Parameter configuration through GUI
* Stimulus timing coordination
* Integration with other device tasks
* Data logging and event recording

Timing Considerations
---------------------

Odor delivery systems have inherent delays:

* **Valve switching time**: Mechanical delay of valve operation
* **Flow transport time**: Time for odor to travel through tubing
* **Mixing chamber dynamics**: Dilution and concentration settling

Account for these delays when designing experimental protocols.

Implementation Notes
--------------------

This is a base class for odor delivery systems. Specific implementations should inherit from this class and implement hardware-specific valve control methods.

Common implementations include:
* DAQ-based valve control with digital outputs
* Serial/USB valve controller interfaces
* Custom hardware interface implementations

Dependencies
------------

* Valve control hardware (implementation-specific)
* Odor delivery manifold system
* Appropriate tubing and fittings
* Odor sources and dilution systems