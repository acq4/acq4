ZeissLamp
=========

.. currentmodule:: acq4.devices.zeiss.ZeissLamp

.. autoclass:: ZeissLamp
    :members:
    :show-inheritance:

Light source for a Zeiss transmitted- or reflected-light lamp via the MTB API.

Configuration
-------------

* **transOrReflect** (str, optional): ``'Transmissive'`` (default) or ``'Reflective'``
* **ZeissMtbComponentID** (str, optional): MTB component ID; takes precedence over **transOrReflect**
* **apiDllLocation** (str, optional): path to ``MTBApi.dll``; standard location if omitted
* Standard LightSource options such as **parentDevice** and **transform**

Example configuration::

    ZeissLamp:
        driver: 'ZeissLamp'
        transOrReflect: 'Transmissive'
        parentDevice: 'Microscope'

Features
--------

* One source, named by the lamp's component ID, with adjustable brightness
* On/off control and brightness (the API uses 0-100; the device uses 0-1)
* ``sigLightChanged`` emitted on lamp change and settle events

Dependencies
------------

* Zeiss MTB API (``MTBApi.dll``) via ``acq4.drivers.zeiss``
