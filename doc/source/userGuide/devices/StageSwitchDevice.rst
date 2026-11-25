StageSwitch
===========

.. currentmodule:: acq4.devices.StageSwitch

.. autoclass:: StageSwitch
    :members:
    :show-inheritance:

Switch device whose value is derived from stage position, e.g. a stage axis that selects between objectives.

Configuration
-------------

* **switches** (dict, required): one entry per switch name, each containing:

  * **device** (str): name of the Stage device to monitor
  * Value keys (int or str) mapping to a tuple of per-axis ``[min, max]`` ranges; ``None`` skips an axis or leaves a bound open

Example configuration::

    MOC:
        driver: 'StageSwitch'
        switches:
            objective:
                device: 'Condenser'
                0: ([None, 0.0445], None, None)
                1: ([0.045, None], None, None)

Features
--------

* ``getSwitch(name)`` returns the current value
* ``sigSwitchChanged`` emits ``{switch_name: value}`` when a position crosses into a new range
* Initial value is the first key listed for each switch until the stage reports a position

Dependencies
------------

* One or more Stage devices
