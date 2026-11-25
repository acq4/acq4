.. _userDevicesThorlabsDC4100:

Thorlabs DC4100
===============

.. currentmodule:: acq4.devices.ThorlabsDC4100

.. autoclass:: ThorlabsDC4100
    :members:
    :undoc-members:
    :show-inheritance:

Thorlabs DC4100 four-channel LED driver, exposed as a LightSource.

Configuration
-------------

* ``port``: serial port (optional; ``None`` is passed to the driver if omitted)
* ``sources``: dict of source name to:

  * ``channel``: LED channel number 1-4 (required; a missing value raises ValueError)
  * ``wavelength``: meters (default: queried from the driver)
  * ``adjustableBrightness``: default True

Example configuration::

    DC4100:
        driver: 'ThorlabsDC4100'
        port: 'COM5'
        sources:
            Blue:
                channel: 1
            Green:
                channel: 2
                wavelength: 525e-9

Features
--------

* Per-channel on/off state read from and written to the hardware
* Per-channel brightness, given as a fraction 0-1 (sent to the driver as percent)

Dependencies
------------

* ``acq4.drivers.ThorlabsDC4100`` driver and the DC4100 hardware
