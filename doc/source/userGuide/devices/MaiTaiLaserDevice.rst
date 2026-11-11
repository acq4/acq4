.. _userDevicesMaiTaiLaser:

Spectra-Physics Mai Tai lasers
==============================

.. note::

    This device was contributed for an older version of ACQ4 and has since been ported to the current codebase, but it has not been tested on hardware since. Expect to need some fixes before it works.

ACQ4 supports Spectra-Physics Mai Tai tunable Ti:sapphire lasers with all of the features provided by the generic :ref:`Laser <userDevicesLaser>` device class. Additionally, serial communication with the laser supports:

* Turning the laser on and off (waiting for warmup to complete) and operating its internal shutter
* Wavelength control
* Pump mode selection (current %, IR power, green power) and pump setpoints
* Monitoring of output power, pump power and current, cavity humidity, pulsing state, P2 optimization, and system and pump laser status codes
* A low-power alignment mode that disables P2 optimization and regulates pump power to hold the output near a configured target

.. currentmodule:: acq4.devices.MaiTaiLaser

.. autoclass:: MaiTaiLaser
    :show-inheritance:
