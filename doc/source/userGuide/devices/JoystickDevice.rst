.. _userDevicesJoystick:

Joystick
========

.. currentmodule:: acq4.devices.Joystick

.. autoclass:: Joystick
    :members:
    :show-inheritance:

A USB/Bluetooth joystick or game controller read through pygame.

Configuration
-------------

Example configuration::

    Joystick1:
        driver: 'Joystick'
        index: 0

or::

    Joystick1:
        driver: 'Joystick'
        name: 'Xbox Controller'

* ``index``: joystick index.
* ``name``: joystick name as reported by pygame (used if ``index`` is absent).
* One of ``index`` or ``name`` is required.
* ``printEvents`` (optional, default False): print each event.

Features
--------

* ``sigStateChanged(self, change)`` is emitted for each axis motion (``{'axis', 'value'}``) or
  button press/release (``{'button', 'value'}``).
* ``state()`` returns a copy of the current ``{'axes': [...], 'buttons': [...]}`` state.
* Events are polled every 20 ms by a background thread.

Dependencies
------------

* ``pygame``
