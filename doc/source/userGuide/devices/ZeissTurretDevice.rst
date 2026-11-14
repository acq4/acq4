ZeissTurret
===========

.. currentmodule:: acq4.devices.zeiss.ZeissTurret

.. autoclass:: ZeissTurret
    :members:
    :show-inheritance:

Filter-wheel device for a Zeiss reflector or objective changer via the MTB API.

Configuration
-------------

* **componentId** (str, optional): ``'MTBReflectorChanger'`` (default); any other value selects the objective changer
* **apiDllLocation** (str, optional): path to ``MTBApi.dll``; standard location if omitted
* Standard FilterWheel options such as **filters**, **parentDevice** and **transform**

Example configuration::

    ZeissReflectorTurret:
        driver: 'ZeissTurret'
        componentId: 'MTBReflectorChanger'
        parentDevice: 'Microscope'
        filters:
            0:
                name: 'FITC'
            1:
                name: 'DAPI'

Features
--------

* Positions are 0-based in ACQ4 and 1-based in the API
* Move futures fail if the target position is not reached
* Device GUI adds previous/next buttons that wrap around
* ``stop``, ``setSpeed`` and ``getSpeed`` are unsupported (they emit warnings)

Dependencies
------------

* Zeiss MTB API (``MTBApi.dll``) via ``acq4.drivers.zeiss``
