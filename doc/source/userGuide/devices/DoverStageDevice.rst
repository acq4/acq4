DoverStage
==========

.. currentmodule:: acq4.devices.DoverStage.doverstage

.. autoclass:: DoverStage
    :members:
    :show-inheritance:

Three-axis (x, y, z) stage controlled through the DoverMotion MotionSynergy client.

Configuration
-------------

* **dllPath** (str, required): path to the MotionSynergy DLL passed to the client
* **defaultAcceleration** (float, optional): default acceleration of the smartstage (default 50.0)
* **capabilities** (dict, optional): overrides the default capabilities (position readable and settable on all axes, no limits)

Example configuration::

    Stage:
        driver: 'DoverStage'
        dllPath: 'C:/path/to/MotionSynergy.dll'
        defaultAcceleration: 50.0

Features
--------

* Position updates delivered by callback from the stage control thread
* Moves return a future; the interpreted speed is passed to the driver multiplied by 1e3
* ``targetPosition()`` returns the target of the last move
* ``stop()`` halts the stage immediately

Dependencies
------------

* DoverMotion MotionSynergy DLL and the ``acq4.drivers.dovermotion`` client
