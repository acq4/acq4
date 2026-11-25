.. _userDevicesXKeys:

X-Keys
======

.. currentmodule:: acq4.devices.XKeys

.. autoclass:: XKeys
    :members:
    :show-inheritance:

A P.I. Engineering X-Keys programmable keypad, exposed as a Keyboard device.

Configuration
-------------

Example configuration::

    PIKeyboard:
        driver: 'XKeys'
        index: 0

* ``index`` (default 0): index of the X-Keys device. An invalid index raises an error listing the
  available models.

Features
--------

* ``sigStateChanged`` is emitted with the key-state changes.
* ``getState()`` returns a copy of the current key states.
* Red/blue backlights: ``setBacklight(key, blue, red)`` (0=off, 1=on, 2=flash), ``setBacklights``,
  ``getBacklights``, and ``setIntensity(b1, b2)`` (set to 255, 255 at startup).
* Backlights are turned off and the device closed on quit.

Dependencies
------------

* X-Keys hardware and the ``acq4.drivers.xkeys`` driver
