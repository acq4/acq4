.. _userDevicesFalconTurret:

Falcon Turret
=============

.. currentmodule:: acq4.devices.FalconTurret.falconturret

.. autoclass:: FalconTurret
    :members:
    :undoc-members:
    :show-inheritance:

Falcon Optics motorized filter turret, built on the FilterWheel base class.

Configuration
-------------

* ``configFile``: Falcon configuration file (optional)
* ``initialSlot``: slot to move to after homing (key is required; ``None`` skips the move)
* ``filters``, ``parentDevice``, ``transform``: as for FilterWheel

Example configuration::

    FalconTurret:
        driver: 'FalconTurret'
        configFile: '/path/to/falcon_config.ini'
        initialSlot: 0
        parentDevice: 'Microscope'
        filters:
            0:
                name: 'FITC'
                description: 'Green fluorescence filter'

Features
--------

* Homes at startup if the turret is not already homed
* ``home()`` re-searches the home position; stopping triggers an emergency stop
* Device GUI with "Find Home" and manual jog buttons for diagnosing position problems

Dependencies
------------

* ``falconoptics`` Python package
