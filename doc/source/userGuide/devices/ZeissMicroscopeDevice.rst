ZeissMicroscope
===============

.. currentmodule:: acq4.devices.zeiss.ZeissMicroscope

.. autoclass:: ZeissMicroscope
    :members:
    :show-inheritance:

Microscope device that changes objectives through the Zeiss MTB API.

Configuration
-------------

* **safeFocusDepth** (float, required): focus depth to move to before changing objectives
* **apiDllLocation** (str, optional): path to ``MTBApi.dll``; standard location if omitted
* Standard Microscope options such as **objectives**, **parentDevice** and **transform**

Example configuration::

    ZeissMicroscope:
        driver: 'ZeissMicroscope'
        parentDevice: 'Stage'
        safeFocusDepth: 5e-3
        objectives:
            0:
                5x:
                    name: '5x 0.25na'
                    scale: 2.581e-6

Features
--------

* ``setObjectiveIndex()`` records the focus depth, moves to the safe depth, then changes the objective
* After the changer settles, focus returns to the recorded depth
* Changer positions are 1-based in the API and 0-based in ACQ4; in-between positions (-1) are ignored
* Disconnects from the MTB API on quit

Dependencies
------------

* Zeiss MTB API (``MTBApi.dll``) via ``acq4.drivers.zeiss``
