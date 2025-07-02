MicroManager Stage  
==================

.. currentmodule:: acq4.devices.MicroManagerStage

.. autoclass:: MicroManagerStage
    :members:
    :undoc-members:
    :show-inheritance:

The MicroManagerStage device provides motorized stage control through the MicroManager interface, allowing ACQ4 to work with a wide variety of microscope stages supported by MicroManager's plugin system.

**Note**: This device has been marked as potentially stale. It may require updates to work with current MicroManager versions.

Configuration
-------------

The MicroManagerStage requires specific MicroManager configuration parameters:

* **mmAdapterName**: The MicroManager adapter name for the stage
* **mmDeviceName**: The MicroManager device name for the stage  
* **path**: Optional path to MicroManager installation directory

Example configuration::

    XYStage:
        driver: 'MicroManagerStage'
        mmAdapterName: 'ASITiger'
        mmDeviceName: 'XYStage'
        path: '/Applications/Micro-Manager'

Dependencies
------------

* pymmcore (Python wrapper for MicroManager Core)
* MicroManager installation with matching API versions
* Appropriate MicroManager device adapters for your stage hardware